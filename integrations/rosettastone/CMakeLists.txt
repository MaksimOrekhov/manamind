cmake_minimum_required(VERSION 3.31.6 FATAL_ERROR)

project(ManaMindRosettaBridge LANGUAGES CXX)

if(NOT DEFINED ROSETTA_SOURCE_DIR)
    message(FATAL_ERROR "Set ROSETTA_SOURCE_DIR to the RosettaStone checkout")
endif()

find_package(effolkronium_random CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

add_library(RosettaStone STATIC IMPORTED GLOBAL)
set_target_properties(RosettaStone PROPERTIES
    IMPORTED_LOCATION "${ROSETTA_SOURCE_DIR}/build-mana-py312/lib/RosettaStone.lib"
    INTERFACE_INCLUDE_DIRECTORIES "${ROSETTA_SOURCE_DIR}/Includes"
)

pybind11_add_module(mana_rosetta_bridge bridge.cpp)
set(PYTHON312_DEV_DIR "${ROSETTA_SOURCE_DIR}/build-mana-ninja/python312-dev")
if(NOT EXISTS "${PYTHON312_DEV_DIR}/include/Python.h")
    message(FATAL_ERROR "Python 3.12 development headers are missing: ${PYTHON312_DEV_DIR}/include/Python.h")
endif()
target_include_directories(mana_rosetta_bridge PRIVATE "${PYTHON312_DEV_DIR}/include")
target_link_libraries(mana_rosetta_bridge PRIVATE RosettaStone effolkronium_random nlohmann_json::nlohmann_json)
target_compile_features(mana_rosetta_bridge PRIVATE cxx_std_23)
set_target_properties(mana_rosetta_bridge PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python"
)
