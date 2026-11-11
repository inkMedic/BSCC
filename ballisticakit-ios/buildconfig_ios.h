// Released under the MIT License. See LICENSE for details.
#ifndef BALLISTICA_COMMUNITY_IOS_CONFIG_H_
#define BALLISTICA_COMMUNITY_IOS_CONFIG_H_
#define BA_COMMUNITY_IOS 1
#define BA_PLATFORM "ios"
#define BA_PLATFORM_IOS 1
#define BA_PLATFORM_IOS_TVOS 1
#define BA_ARCH "arm64"
#define BA_VARIANT "generic"
#define BA_VARIANT_GENERIC 1
#define BA_SDL_BUILD 1
#define BA_ENABLE_SDL_JOYSTICKS 1
#define BA_ENABLE_OPENGL 1
#define BA_OPENGL_IS_ES 1
#define BA_ENABLE_AUDIO 1
#define BA_USE_TREMOR_VORBIS 0
#define BA_ENABLE_OS_FONT_RENDERING 1
#define BA_MONOLITHIC_BUILD 1
#define BA_DEFINE_MAIN 0
#define BA_CONTAINS_PYTHON_DIST 1
#define BA_ENABLE_EXECINFO_BACKTRACES 1
#define BA_ENABLE_STDIO_CONSOLE 0
#define GLES_SILENCE_DEPRECATION 1
#define dTRIMESH_ENABLED 1
#if !BA_DEBUG_BUILD
#ifndef NDEBUG
#define NDEBUG 1
#endif
#define dNODEBUG 1
#endif
#include "ballistica/shared/buildconfig/buildconfig_common.h"
#endif
