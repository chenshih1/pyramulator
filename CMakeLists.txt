cmake_minimum_required(VERSION 3.15)
project(pyramulator LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

set(RAMULATOR_SRC ${CMAKE_CURRENT_SOURCE_DIR}/src/ramulator/src)

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

install(TARGETS _core DESTINATION pyramulator)
