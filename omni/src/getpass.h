/* Given to every fossil source file by the compiler's include flag, so fossil's tree stays as released.
** Cosmopolitan declares no getpass(); this one reads over its readpassphrase(). */
#if defined(__COSMOPOLITAN__) && !defined(TKT_APE_GETPASS_H)
#define TKT_APE_GETPASS_H
#include "libc/stdio/readpassphrase.h"
static inline char *getpass(const char *zPrompt){
  static char zBuf[256];
  return readpassphrase(zPrompt, zBuf, sizeof(zBuf), 0);
}
#endif
