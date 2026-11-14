/* Independently implemented from the save-profile workflow described by juvxncio/zelda-oot-perfis.
   Selection happens before guest workers and filesystem mounts exist. No live file redirection. */
#include "save_profile.h"
#include "hos_paths.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

extern void hos_log(const char *, ...);

static int parse_profile(const char *value) {
    if (!value || value[0] < '1' || value[0] > '9') return 0;
    for (const char *p = value + 1; *p; p++)
        if (*p != ' ' && *p != '\t' && *p != '\r' && *p != '\n') return 0;
    return value[0] - '0';
}

static int profile_directory(const char *path) {
    DWORD attr = GetFileAttributesA(path);
    if (attr != INVALID_FILE_ATTRIBUTES)
        return (attr & FILE_ATTRIBUTE_DIRECTORY) && !(attr & FILE_ATTRIBUTE_REPARSE_POINT);
    return CreateDirectoryA(path, NULL) != 0;
}

int hos_save_profile_select(const char *base, char *out, size_t capacity) {
    int profile = 1;
    const char *override = getenv("HOS_SAVE_PROFILE");
    if (override) profile = parse_profile(override);
    else {
        char path[MAX_PATH];
        DWORD n = hos_game_path_a(path, sizeof path);
        char *slash = NULL;
        if (n && n < sizeof path)
            for (char *p = path; *p; p++) if (*p == '/' || *p == '\\') slash = p;
        if (slash && (size_t)(slash + 1 - path) + sizeof "hookshot_options.ini" <= sizeof path) {
            strcpy(slash + 1, "hookshot_options.ini");
            FILE *f = fopen(path, "r");
            if (f) {
                char line[512];
                while (fgets(line, sizeof line, f))
                    if (!strncmp(line, "save_profile=", 13)) profile = parse_profile(line + 13);
                fclose(f);
            }
        }
    }
    if (!profile) {
        hos_log("profiles: invalid save profile; choose 1 through 9. No save folder selected.");
        return 0;
    }
    int n = snprintf(out, capacity, "%s", base);
    if (n < 0 || (size_t)n >= capacity) return 0;
    if (profile == 1) return 1;
    n = snprintf(out, capacity, "%s/profiles", base);
    if (n < 0 || (size_t)n >= capacity || !profile_directory(out)) return 0;
    n = snprintf(out, capacity, "%s/profiles/profile-%d", base, profile);
    if (n < 0 || (size_t)n >= capacity || !profile_directory(out)) return 0;
    hos_log("profiles: save profile %d: %s (the original saves remain in %s)", profile, out, base);
    return 1;
}
