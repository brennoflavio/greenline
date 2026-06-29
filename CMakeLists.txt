cmake_minimum_required(VERSION 3.0.0)
project(greenline C CXX)

find_package(Qt5 REQUIRED COMPONENTS Core Qml Multimedia)

# Automatically create moc files
set(CMAKE_AUTOMOC ON)

execute_process(
    COMMAND dpkg-architecture -qDEB_HOST_MULTIARCH
    OUTPUT_VARIABLE ARCH_TRIPLET
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
set(QT_IMPORTS_DIR "lib/${ARCH_TRIPLET}")

set(PROJECT_NAME "greenline")
set(FULL_PROJECT_NAME "greenline.brennoflavio")
set(DATA_DIR /)
set(DESKTOP_FILE_NAME ${PROJECT_NAME}.desktop)

# This command figures out the minimum SDK framework for use in the manifest
# file via the environment variable provided by Clickable or sets a default value otherwise.
if(DEFINED ENV{SDK_FRAMEWORK})
    set(CLICK_FRAMEWORK "$ENV{SDK_FRAMEWORK}")
else()
    set(CLICK_FRAMEWORK "ubuntu-sdk-20.04")
endif()

# This figures out the target architecture for use in the manifest file.
if(DEFINED ENV{ARCH})
    set(CLICK_ARCH "$ENV{ARCH}")
else()
    execute_process(
        COMMAND dpkg-architecture -qDEB_HOST_ARCH
        OUTPUT_VARIABLE CLICK_ARCH
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
endif()

if(DEFINED ENV{GREENLINE_BUILD_VERSION} AND NOT "$ENV{GREENLINE_BUILD_VERSION}" STREQUAL "")
  set(BUILD_VERSION "$ENV{GREENLINE_BUILD_VERSION}")
else()
  string(TIMESTAMP BUILD_VERSION "%y%m%d%H%M%S" UTC)
endif()

if(NOT BUILD_VERSION MATCHES "^[0-9][0-9A-Za-z.+:~-]*$")
  message(FATAL_ERROR "Build version '${BUILD_VERSION}' is not dpkg-safe")
endif()

message(STATUS "Build version is: ${BUILD_VERSION}")
add_definitions(-DBUILD_VERSION="${BUILD_VERSION}")
file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/build-version.txt "${BUILD_VERSION}")
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/build-version.txt DESTINATION ${DATA_DIR}src)

# Git commit hash for daemon version checking
if(DEFINED ENV{GITHUB_SHA} AND NOT "$ENV{GITHUB_SHA}" STREQUAL "")
  set(GIT_COMMIT_HASH "$ENV{GITHUB_SHA}")
else()
  execute_process(
    COMMAND git rev-parse HEAD
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE GIT_COMMIT_HASH
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
  )
endif()
if(NOT GIT_COMMIT_HASH)
  message(FATAL_ERROR "Could not resolve git commit hash for version.txt")
endif()
message(STATUS "Git commit hash is: ${GIT_COMMIT_HASH}")
file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/version.txt "${GIT_COMMIT_HASH}")
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/version.txt DESTINATION ${DATA_DIR}src)

configure_file(manifest.json.in ${CMAKE_CURRENT_BINARY_DIR}/manifest.json)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/manifest.json DESTINATION ${CMAKE_INSTALL_PREFIX})
install(FILES ${PROJECT_NAME}.apparmor DESTINATION ${DATA_DIR})
install(FILES ${PROJECT_NAME}.dispatcher DESTINATION ${DATA_DIR})
install(FILES ${PROJECT_NAME}-contenthub.json DESTINATION ${DATA_DIR})

install(DIRECTORY assets DESTINATION ${DATA_DIR})
install(DIRECTORY src DESTINATION ${DATA_DIR})

install(DIRECTORY qml DESTINATION ${DATA_DIR})

add_library(audiocaptureplugin MODULE
    plugin/audiocapture/audiocapturerecorder.cpp
    plugin/audiocapture/plugin.cpp
)
target_link_libraries(audiocaptureplugin PRIVATE Qt5::Core Qt5::Qml Qt5::Multimedia)
install(TARGETS audiocaptureplugin LIBRARY DESTINATION ${DATA_DIR}qml/AudioCapture)

# Golang Daemon
install(FILES "build-daemon.sh" DESTINATION ${DATA_DIR})
install(DIRECTORY daemon DESTINATION ${DATA_DIR})

# Python Deps
install(FILES "build-python-deps.sh" DESTINATION ${DATA_DIR})
install(FILES "uv.lock" DESTINATION ${DATA_DIR})
install(FILES "pyproject.toml" DESTINATION ${DATA_DIR})

# Push Notifications
install(FILES pushexec PERMISSIONS OWNER_EXECUTE OWNER_WRITE OWNER_READ DESTINATION ${DATA_DIR})
install(FILES push.json DESTINATION ${DATA_DIR})
install(FILES push.apparmor DESTINATION ${DATA_DIR})

# Translations
file(GLOB_RECURSE I18N_SRC_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}/po qml/*.qml qml/*.js)
list(APPEND I18N_SRC_FILES ${DESKTOP_FILE_NAME}.in.h)

find_program(INTLTOOL_MERGE intltool-merge)
if(NOT INTLTOOL_MERGE)
    message(FATAL_ERROR "Could not find intltool-merge, please install the intltool package")
endif()
find_program(INTLTOOL_EXTRACT intltool-extract)
if(NOT INTLTOOL_EXTRACT)
    message(FATAL_ERROR "Could not find intltool-extract, please install the intltool package")
endif()

add_custom_target(${DESKTOP_FILE_NAME} ALL
    COMMENT "Merging translations into ${DESKTOP_FILE_NAME}..."
    COMMAND LC_ALL=C ${INTLTOOL_MERGE} -d -u ${CMAKE_SOURCE_DIR}/po ${CMAKE_SOURCE_DIR}/${DESKTOP_FILE_NAME}.in ${DESKTOP_FILE_NAME}
    COMMAND sed -i 's/${PROJECT_NAME}-//g' ${CMAKE_CURRENT_BINARY_DIR}/${DESKTOP_FILE_NAME}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/${DESKTOP_FILE_NAME} DESTINATION ${DATA_DIR})

add_subdirectory(po)

# Make source files visible in qtcreator
file(GLOB_RECURSE PROJECT_SRC_FILES
    RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}
    qml/*.qml
    qml/*.js
    qml/*/qmldir
    src/*
    plugin/*.cpp
    plugin/*.h
    plugin/*/*.cpp
    plugin/*/*.h
    *.json
    *.json.in
    *.apparmor
    *.desktop.in
)

add_custom_target(${PROJECT_NAME}_FILES ALL SOURCES ${PROJECT_SRC_FILES})
