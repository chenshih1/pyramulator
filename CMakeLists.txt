cmake_minimum_required(VERSION 3.15)
project(pyramulator LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

# ---------------------------------------------------------------------------
# Ramulator is an external dependency. Prefer the git submodule at
# third_party/ramulator; fall back to fetching from upstream when it is
# absent (e.g. when building from an sdist). The bindings use only
# ramulator's public API (same calls as its own Gem5Wrapper), so no
# ramulator source is modified.
# ---------------------------------------------------------------------------
set(RAMULATOR_TAG "214f635845214adf030367939655d172ef0fed5f")

set(RAMULATOR_SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/ramulator)
if(NOT EXISTS ${RAMULATOR_SOURCE_DIR}/src/Config.h)
  message(STATUS "ramulator submodule not found, fetching from upstream")
  include(FetchContent)
  FetchContent_Declare(
    ramulator
    GIT_REPOSITORY https://github.com/CMU-SAFARI/ramulator.git
    GIT_TAG ${RAMULATOR_TAG}
    GIT_SHALLOW TRUE
  )
  FetchContent_GetProperties(ramulator)
  if(NOT ramulator_POPULATED)
    FetchContent_Populate(ramulator)
  endif()
  set(RAMULATOR_SOURCE_DIR ${ramulator_SOURCE_DIR})
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

pybind11_add_module(_core src/bindings.cpp ${RAMULATOR_SOURCES})

target_include_directories(_core PRIVATE ${RAMULATOR_SRC})
target_compile_definitions(_core PRIVATE RAMULATOR)
target_compile_options(_core PRIVATE -O3)

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
