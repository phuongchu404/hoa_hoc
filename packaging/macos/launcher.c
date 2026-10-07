/* ChemImage.app/Contents/MacOS/ChemImage
 * Starts the bundled Python (Contents/Resources/python) and runs
 * `app.desktop` from Contents/Resources/backend. Being the bundle's own
 * executable gives the app its name and icon in the Dock. */
#include <Python.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    (void)argc;
    char exe[PATH_MAX], real[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0 || realpath(exe, real) == NULL) {
        fprintf(stderr, "ChemImage: cannot locate executable\n");
        return 1;
    }
    char macos[PATH_MAX];
    strncpy(macos, dirname(real), sizeof(macos) - 1);
    macos[sizeof(macos) - 1] = 0;

    char home[PATH_MAX], backend[PATH_MAX];
    snprintf(home, sizeof(home), "%s/../Resources/python", macos);
    snprintf(backend, sizeof(backend), "%s/../Resources/backend", macos);
    char rhome[PATH_MAX], rbackend[PATH_MAX];
    if (!realpath(home, rhome) || !realpath(backend, rbackend)) {
        fprintf(stderr, "ChemImage: bundle is incomplete\n");
        return 1;
    }

    /* ignore whatever Python the user may have configured */
    unsetenv("PYTHONHOME");
    unsetenv("PYTHONSTARTUP");
    unsetenv("VIRTUAL_ENV");
    setenv("PYTHONPATH", rbackend, 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
    setenv("HF_HUB_OFFLINE", "1", 1);
    setenv("TRANSFORMERS_OFFLINE", "1", 1);
    setenv("PYTORCH_ENABLE_MPS_FALLBACK", "1", 1);
    chdir(rbackend);

    PyStatus status;
    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    config.write_bytecode = 0;
    status = PyConfig_SetBytesString(&config, &config.home, rhome);
    if (PyStatus_Exception(status)) goto fail;
    status = PyConfig_SetBytesString(&config, &config.program_name, argv[0]);
    if (PyStatus_Exception(status)) goto fail;
    status = PyConfig_SetString(&config, &config.run_module, L"app.desktop");
    if (PyStatus_Exception(status)) goto fail;
    char *args[] = {argv[0]};  /* drop LaunchServices' -psn_ argument */
    status = PyConfig_SetBytesArgv(&config, 1, args);
    if (PyStatus_Exception(status)) goto fail;
    status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status)) goto fail;
    PyConfig_Clear(&config);
    return Py_RunMain();

fail:
    PyConfig_Clear(&config);
    Py_ExitStatusException(status);
}
