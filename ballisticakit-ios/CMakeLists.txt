cmake_minimum_required(VERSION 3.28)
project(BallisticaCommunityIOS LANGUAGES C CXX OBJC OBJCXX)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" OR NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
  message(FATAL_ERROR "Use tools/community-ios/build.py with an arm64 Apple SDK")
endif()
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_OBJCXX_STANDARD 23)
get_filename_component(ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(DEPS "${ROOT}/build/community-ios-deps")
set(PYROOT "${ROOT}/build/python_apple_${APPLE_SDK}_arm64")
set(BA_SRC_ROOT "${ROOT}/src")
set(ODE_SRC_ROOT "${BA_SRC_ROOT}/external/open_dynamics_engine-ef")
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
add_subdirectory("${DEPS}/SDL" "${CMAKE_BINARY_DIR}/sdl" EXCLUDE_FROM_ALL)
set(INSTALL_DOCS OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory("${DEPS}/ogg" "${CMAKE_BINARY_DIR}/ogg" EXCLUDE_FROM_ALL)
# Vorbis's finder recognizes the in-tree Ogg target.
set(OGG_INCLUDE_DIR "${DEPS}/ogg/include" CACHE PATH "" FORCE)
set(OGG_LIBRARY ogg CACHE STRING "" FORCE)
add_subdirectory("${DEPS}/vorbis" "${CMAKE_BINARY_DIR}/vorbis" EXCLUDE_FROM_ALL)
set(LIBTYPE STATIC CACHE STRING "" FORCE)
set(ALSOFT_EXAMPLES OFF CACHE BOOL "" FORCE)
set(ALSOFT_UTILS OFF CACHE BOOL "" FORCE)
set(ALSOFT_TESTS OFF CACHE BOOL "" FORCE)
set(ALSOFT_INSTALL OFF CACHE BOOL "" FORCE)
set(ALSOFT_BACKEND_PORTAUDIO OFF CACHE BOOL "" FORCE)
add_subdirectory("${DEPS}/openal" "${CMAKE_BINARY_DIR}/openal" EXCLUDE_FROM_ALL)
add_library(common_deps INTERFACE)
target_include_directories(common_deps INTERFACE "${BA_SRC_ROOT}" "${CMAKE_CURRENT_LIST_DIR}")
target_compile_options(common_deps INTERFACE -include "${CMAKE_CURRENT_LIST_DIR}/buildconfig_ios.h")
target_compile_definitions(common_deps INTERFACE $<$<CONFIG:Debug>:BA_DEBUG_BUILD=1>)
# Read the same fixed source blocks as the Android community build. Do not
# evaluate upstream desktop dependency discovery or proprietary Plus linkage.
file(READ "${ROOT}/ballisticakit-cmake/CMakeLists.txt" upstream)
function(source_block start_text output)
  string(FIND "${upstream}" "${start_text}" start)
  if(start LESS 0)
    message(FATAL_ERROR "Upstream source list changed")
  endif()
  string(SUBSTRING "${upstream}" ${start} -1 rest)
  string(FIND "${rest}" "\n)" end)
  if(end LESS 0)
    message(FATAL_ERROR "Unterminated source block")
  endif()
  math(EXPR length "${end} + 2")
  string(SUBSTRING "${rest}" 0 ${length} block)
  set(${output} "${block}" PARENT_SCOPE)
endfunction()
source_block("add_library(ode\n" ode_block)
source_block("set(BALLISTICA_SOURCES\n" engine_block)
file(WRITE "${CMAKE_BINARY_DIR}/upstream-sources.cmake" "${ode_block}\n${engine_block}\n")
include("${CMAKE_BINARY_DIR}/upstream-sources.cmake")
list(FILTER BALLISTICA_SOURCES EXCLUDE REGEX "/core/platform/apple/platform_apple\\.")
target_include_directories(ode PRIVATE "${ODE_SRC_ROOT}")
target_link_libraries(ode PRIVATE common_deps)
add_executable(BallisticaCommunity MACOSX_BUNDLE ${BALLISTICA_SOURCES}
  main.mm platform_ios.mm frame_clock_ios.mm metal_presenter_ios.mm
  "${BA_SRC_ROOT}/ballistica/plus/community_plus.cc")
target_include_directories(BallisticaCommunity PRIVATE "${ODE_SRC_ROOT}"
  "${PYROOT}/include" "${DEPS}/ogg/include" "${DEPS}/vorbis/include"
  "${DEPS}/openal/include/AL" "${BA_SRC_ROOT}/external/zstd/include")
target_link_libraries(BallisticaCommunity PRIVATE common_deps ode SDL3::SDL3-static
  vorbisfile vorbis ogg OpenAL "${PYROOT}/libpython_merged.a"
  "-framework UIKit" "-framework Foundation" "-framework CoreText"
  "-framework Security" "-framework OpenGLES" "-framework Metal" "-framework IOSurface" "-framework QuartzCore"
  "-framework AudioToolbox"
  "-framework AVFAudio" "-framework AVFoundation" "-framework SystemConfiguration" z iconv sqlite3)
target_sources(BallisticaCommunity PRIVATE Assets.xcassets)
set_source_files_properties(Assets.xcassets PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
set_source_files_properties(main.mm platform_ios.mm frame_clock_ios.mm metal_presenter_ios.mm
  PROPERTIES COMPILE_FLAGS "-fobjc-arc")
set_target_properties(BallisticaCommunity PROPERTIES
  XCODE_GENERATE_SCHEME TRUE
  XCODE_SCHEME_LAUNCH_CONFIGURATION Release
  XCODE_ATTRIBUTE_CODE_SIGN_IDENTITY "Apple Development"
  MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_LIST_DIR}/Info.plist.in"
  XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${COMMUNITY_BUNDLE_ID}"
  XCODE_ATTRIBUTE_ASSETCATALOG_COMPILER_APPICON_NAME AppIcon
  XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
  XCODE_ATTRIBUTE_ENABLE_USER_SCRIPT_SANDBOXING NO
  XCODE_ATTRIBUTE_CODE_SIGN_STYLE Automatic
  XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${COMMUNITY_TEAM_ID}"
  XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "${COMMUNITY_SIGNING}")
if(NOT COMMUNITY_COMPILE_ONLY)
add_custom_command(TARGET BallisticaCommunity POST_BUILD
  COMMAND "${COMMUNITY_PYTHON}" "${ROOT}/tools/community-ios/stage_bundle.py"
    "${ROOT}/build/community-ios-stage/${APPLE_SDK}" "$<TARGET_BUNDLE_DIR:BallisticaCommunity>"
  COMMENT "Staging Python, scripts and verified mobile assets")
endif()
