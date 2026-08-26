cmake_minimum_required(VERSION 3.20)
project(pyramulator LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
endif()

# Emit per-function/per-data sections and let the linker drop the ones we
# never call: the vendored simulator ships many standards/technologies the
# wrapper can never exercise in a single run.
# ---------------------------------------------------------------------------
# Profile-Guided Optimization (PGO).
#   PYRAMULATOR_PGO_MODE=OFF    — default, no PGO
#   PYRAMULATOR_PGO_MODE=GENERATE — instrumented build for profile collection
#   PYRAMULATOR_PGO_MODE=USE    — optimized build using collected profiles
# ---------------------------------------------------------------------------
set(PYRAMULATOR_PGO_MODE "OFF" CACHE STRING "PGO mode: OFF, GENERATE, or USE")
set_property(CACHE PYRAMULATOR_PGO_MODE PROPERTY STRINGS OFF GENERATE USE)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-ffunction-sections -fdata-sections)
    if(CMAKE_BUILD_TYPE STREQUAL "Release")
        add_compile_options(-march=native -mtune=native)
    endif()
    if(APPLE)
        add_link_options("-Wl,-dead_strip")
    else()
        add_link_options("-Wl,--gc-sections")
    endif()
    # PGO flags (GCC/Clang on Linux; ignored on Apple in CI, kept simple)
    if(NOT PYRAMULATOR_PGO_MODE STREQUAL "OFF")
        if(NOT DEFINED PYRAMULATOR_PGO_DIR)
            set(PYRAMULATOR_PGO_DIR "${CMAKE_BINARY_DIR}/pgo-data")
        endif()
        if(PYRAMULATOR_PGO_MODE STREQUAL "GENERATE")
            file(MAKE_DIRECTORY ${PYRAMULATOR_PGO_DIR})
            add_compile_options(-fprofile-generate=${PYRAMULATOR_PGO_DIR})
            add_link_options(-fprofile-generate=${PYRAMULATOR_PGO_DIR})
        elseif(PYRAMULATOR_PGO_MODE STREQUAL "USE")
            add_compile_options(-fprofile-use=${PYRAMULATOR_PGO_DIR})
            add_link_options(-fprofile-use=${PYRAMULATOR_PGO_DIR})
        endif()
    endif()
endif()

# Whole-program optimization across the binding and the vendored simulator.
# Release-only so debug rebuilds stay fast; degrades gracefully on
# toolchains without IPO support.
include(CheckIPOSupported)
check_ipo_supported(RESULT _ipo_supported)
if(_ipo_supported)
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE ON)
else()
    message(STATUS "LTO/IPO not supported by this toolchain; skipping")
endif()

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

# ---------------------------------------------------------------------------
# Ramulator is an external dependency. Prefer the git submodule at
# third_party/ramulator; fall back to downloading the pinned source tarball
# when it is absent (e.g. when building from an sdist). The bindings use
# only ramulator's public API (same calls as its own Gem5Wrapper), so no
# ramulator source is modified.
#
# git smart-HTTP to github.com is unreliable on some networks, so the
# auto-fetch downloads the pinned commit's tarball from codeload (or a
# configured mirror) with retries instead of git clone/FetchContent.
# ---------------------------------------------------------------------------
set(RAMULATOR_TAG "214f635845214adf030367939655d172ef0fed5f")

set(RAMULATOR_SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/ramulator)
if(NOT EXISTS ${RAMULATOR_SOURCE_DIR}/src/Config.h)
    option(PYRAMULATOR_FETCH_RAMULATOR
        "Auto-download the vendored Ramulator when missing" ON)
    set(PYRAMULATOR_RAMULATOR_TARBALL_URL
        "https://codeload.github.com/CMU-SAFARI/ramulator/tar.gz/${RAMULATOR_TAG}"
        CACHE STRING
        "Source tarball to fetch Ramulator from when auto-fetch is enabled")
    set(PYRAMULATOR_FETCH_RETRIES 3 CACHE STRING
        "Auto-fetch download attempts before giving up")

    if(PYRAMULATOR_FETCH_RAMULATOR)
        message(STATUS
            "ramulator submodule not found; downloading pinned source ${RAMULATOR_TAG}")
        set(_ramu_tar "${CMAKE_BINARY_DIR}/ramulator-${RAMULATOR_TAG}.tar.gz")
        set(_ramu_fetch_ok FALSE)
        foreach(_attempt RANGE 1 ${PYRAMULATOR_FETCH_RETRIES})
            file(DOWNLOAD "${PYRAMULATOR_RAMULATOR_TARBALL_URL}" "${_ramu_tar}"
                STATUS _ramu_dl_status TIMEOUT 600 SHOW_PROGRESS)
            list(GET _ramu_dl_status 0 _ramu_dl_code)
            if(_ramu_dl_code EQUAL 0)
                set(_ramu_fetch_ok TRUE)
                break()
            endif()
            message(STATUS
                "ramulator download failed (attempt ${_attempt}/${PYRAMULATOR_FETCH_RETRIES})")
        endforeach()
        if(NOT _ramu_fetch_ok)
            message(FATAL_ERROR
                "Failed to download Ramulator from ${PYRAMULATOR_RAMULATOR_TARBALL_URL}.\n"
                "Check your network connection, or run: git submodule update --init")
        endif()
        execute_process(
            COMMAND ${CMAKE_COMMAND} -E tar xzf "${_ramu_tar}"
            WORKING_DIRECTORY "${CMAKE_BINARY_DIR}"
            RESULT_VARIABLE _ramu_tar_result
        )
        if(NOT _ramu_tar_result EQUAL 0)
            message(FATAL_ERROR "Failed to extract the Ramulator tarball")
        endif()
        file(GLOB _ramu_extracted "${CMAKE_BINARY_DIR}/ramulator-*")
        if(NOT _ramu_extracted)
            message(FATAL_ERROR
                "Ramulator tarball extracted to an unexpected directory layout")
        endif()
        list(GET _ramu_extracted 0 _ramu_extracted_dir)
        file(RENAME "${_ramu_extracted_dir}" "${CMAKE_BINARY_DIR}/ramulator-src")
        set(RAMULATOR_SOURCE_DIR "${CMAKE_BINARY_DIR}/ramulator-src")
        if(NOT EXISTS ${RAMULATOR_SOURCE_DIR}/src/Config.h)
            message(FATAL_ERROR "Fetched Ramulator tree is missing src/Config.h")
        endif()
        message(STATUS "Ramulator fetched to ${RAMULATOR_SOURCE_DIR}")
    else()
        message(FATAL_ERROR "Ramulator not found at 'third_party/ramulator'.\n"
                            "Please run: git submodule update --init")
    endif()
endif()

# ramulator is maintained with a Makefile, so the sources are compiled
# directly into the _core module instead of via add_subdirectory.
set(RAMULATOR_SRC ${RAMULATOR_SOURCE_DIR}/src)

set(RAMULATOR_SOURCES
    ${RAMULATOR_SRC}/Config.cpp
    ${RAMULATOR_SRC}/Controller.cpp
    ${RAMULATOR_SRC}/MemoryFactory.cpp
    ${RAMULATOR_SRC}/Refresh.cpp
    ${RAMULATOR_SRC}/DDR3.cpp
    ${RAMULATOR_SRC}/DDR4.cpp
    ${RAMULATOR_SRC}/LPDDR3.cpp
    ${RAMULATOR_SRC}/LPDDR4.cpp
    ${RAMULATOR_SRC}/GDDR5.cpp
    ${RAMULATOR_SRC}/WideIO.cpp
    ${RAMULATOR_SRC}/WideIO2.cpp
    ${RAMULATOR_SRC}/HBM.cpp
    ${RAMULATOR_SRC}/SALP.cpp
    ${RAMULATOR_SRC}/ALDRAM.cpp
    ${RAMULATOR_SRC}/DSARP.cpp
    ${RAMULATOR_SRC}/PCM.cpp
    ${RAMULATOR_SRC}/STTMRAM.cpp
    ${RAMULATOR_SRC}/TLDRAM.cpp
    ${RAMULATOR_SRC}/StatType.cpp
)

pybind11_add_module(_core cpp/bindings.cpp ${RAMULATOR_SOURCES})

target_include_directories(_core PRIVATE ${RAMULATOR_SRC})
target_compile_definitions(_core PRIVATE RAMULATOR)

# Scope strict warnings to our own binding sources only; the vendored
# simulator compiles with its own (unset) warning policy.
if(MSVC)
    set_source_files_properties(cpp/bindings.cpp PROPERTIES COMPILE_OPTIONS /W4)
else()
    set_source_files_properties(cpp/bindings.cpp PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra")
endif()

# ramulator's StatType.h uses uintN_t without including <cstdint>; it
# compiles by accident on some toolchains via transitive includes but fails
# on others. Force the header in without modifying ramulator sources.
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(_core PRIVATE -include cstdint)
elseif(MSVC)
  target_compile_options(_core PRIVATE /FI cstdint)
endif()

install(TARGETS _core DESTINATION pyramulator)

# Ship the ramulator reference configs so Config.from_file keeps working
# without the vendored dependency tree.
file(GLOB RAMULATOR_CONFIGS ${RAMULATOR_SOURCE_DIR}/configs/*.cfg)
install(FILES ${RAMULATOR_CONFIGS} DESTINATION pyramulator/data/configs)
