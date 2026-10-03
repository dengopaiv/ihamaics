# engine/ - the C17 rewrite of the SAM engine.
#
# Plan: docs/c17-rewrite-plan.md. Stage log: docs/c17/.
# native/ is the frozen reference this is checked against, with the
# Python in nvda-addon/synthDrivers/sam as the oracle behind both.
#
# Build (any of the four legs in docs/c17-rewrite-plan.md section 3.4):
#   cmake -S engine -B engine/build-msvc -G Ninja
#   cmake --build engine/build-msvc
#   ctest --test-dir engine/build-msvc

cmake_minimum_required(VERSION 3.16)

# One version number for the whole project, and it lives in the addon
# manifest. gui-native/sam_gui.rc copies it and tools/make_release.py
# checks the copy; this reads it rather than adding a third copy.
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/../nvda-addon/manifest.ini"
     _sam_version_line REGEX "^version[ \t]*=")
string(REGEX MATCH "[0-9]+\\.[0-9]+\\.[0-9]+" SAM_VERSION "${_sam_version_line}")
if(NOT SAM_VERSION)
    message(FATAL_ERROR "no version found in nvda-addon/manifest.ini")
endif()

# Release unless told otherwise. This has to come before project(): on
# Windows, project() fills in Debug itself, and a test after it never
# fires. Found in stage R.0, when the MSVC leg came out with /Od /RTC1.
if(NOT DEFINED CMAKE_BUILD_TYPE AND NOT DEFINED ENV{CMAKE_BUILD_TYPE})
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type")
endif()

project(sam_engine VERSION ${SAM_VERSION} LANGUAGES C)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

# No 32-bit build of anything, by house rule.
if(CMAKE_SIZEOF_VOID_P EQUAL 4)
    message(FATAL_ERROR "32-bit builds are not produced; configure for x64 or ARM64")
endif()

# Warnings. No -Werror: a clean build on every leg is part of each
# stage's exit test, checked by reading the log, so a new compiler's new
# warning does not break a checkout.
if(MSVC)
    set(SAM_WARNINGS /W4)
    set(SAM_DEFINES _CRT_SECURE_NO_WARNINGS)
else()
    set(SAM_WARNINGS -Wall -Wextra -Wpedantic -Wshadow -Wconversion)
    set(SAM_DEFINES)
endif()

set(SAM_SOURCES
    src/version.c
    src/tables.c
    src/voice.c
    src/frames.c
    src/render.c
)

# The same sources twice: a static library for the tools and tests, and
# a shared one that is what the addon and the GUI load. Only the SAM_API
# entry points are exported.
add_library(sam_static STATIC ${SAM_SOURCES})
add_library(sam_shared SHARED ${SAM_SOURCES})
set_target_properties(sam_shared PROPERTIES OUTPUT_NAME sam_render)
target_compile_definitions(sam_shared PRIVATE SAM_BUILD_DLL)

foreach(t sam_static sam_shared)
    target_include_directories(${t} PUBLIC include PRIVATE src)
    target_compile_options(${t} PRIVATE ${SAM_WARNINGS})
    target_compile_definitions(${t} PRIVATE ${SAM_DEFINES})
    set_target_properties(${t} PROPERTIES C_VISIBILITY_PRESET hidden)
endforeach()

include(CTest)
if(BUILD_TESTING)
    add_executable(test_abi tests/test_abi.c)
    target_link_libraries(test_abi PRIVATE sam_static)
    target_compile_options(test_abi PRIVATE ${SAM_WARNINGS})
    add_test(NAME abi COMMAND test_abi)
    set_tests_properties(abi PROPERTIES LABELS quick)

    # sam_render's contract, on two golden vectors (stage R.4). Runs on
    # every leg, so Linux checks golden samples before the verifiers do.
    add_executable(test_render tests/test_render.c)
    target_link_libraries(test_render PRIVATE sam_static)
    target_compile_options(test_render PRIVATE ${SAM_WARNINGS})
    target_compile_definitions(test_render PRIVATE ${SAM_DEFINES})
    add_test(NAME render COMMAND test_render
             "${CMAKE_CURRENT_SOURCE_DIR}/../native/tests/golden")
    set_tests_properties(render PROPERTIES LABELS quick)

    # The dump tools: one per boundary the verifiers check, each printing
    # what its namesake in native/tools prints. They go in the top of the
    # build tree, where native/tools/_build.py looks for them.
    foreach(tool dump_tables dump_frames dump_prepare dump_render)
        add_executable(${tool} tools/${tool}.c)
        target_link_libraries(${tool} PRIVATE sam_static)
        target_include_directories(${tool} PRIVATE src)
        target_compile_options(${tool} PRIVATE ${SAM_WARNINGS})
        target_compile_definitions(${tool} PRIVATE ${SAM_DEFINES})
    endforeach()

    # The differential verifiers in native/tools, run against this build
    # (--impl engine, with SAM_ENGINE_BUILD naming this leg's tree). Each
    # exits 77 - a skip, not a failure - until the stage that gives the
    # rewrite its dump tool, so the list is complete from R.0 and every
    # stage turns its own entries from skipped to passed.
    #
    # Windows only for now: the verifiers look for .exe dump tools and a
    # .dll. The Linux legs are verified from Windows in stage R.10.
    find_package(Python3 COMPONENTS Interpreter)

    # Generated sources still agree with the Python they come from. Needs
    # only Python, so it runs on every leg, Linux included.
    if(Python3_Interpreter_FOUND)
        add_test(NAME tables_current
                 COMMAND Python3::Interpreter
                         "${CMAKE_CURRENT_SOURCE_DIR}/tools/gen_tables.py" --check)
        set_tests_properties(tables_current PROPERTIES LABELS quick)
    endif()

    if(WIN32 AND Python3_Interpreter_FOUND)
        set(SAM_TOOLS "${CMAKE_CURRENT_SOURCE_DIR}/../native/tools")
        # name, then arguments; counts are the exit tests of the plan.
        set(SAM_VERIFIERS
            "tables"
            "frames"
            "prepare\;3000"
            "render\;485"
            "parser"
            "reciter"
            "text")
        foreach(entry IN LISTS SAM_VERIFIERS)
            list(GET entry 0 name)
            set(args)
            list(LENGTH entry n)
            if(n GREATER 1)
                list(SUBLIST entry 1 -1 args)
            endif()
            add_test(NAME verify_${name}
                     COMMAND Python3::Interpreter "${SAM_TOOLS}/verify_${name}.py"
                             --impl engine ${args})
            set_tests_properties(verify_${name} PROPERTIES
                LABELS validation
                SKIP_RETURN_CODE 77
                ENVIRONMENT "SAM_ENGINE_BUILD=${CMAKE_BINARY_DIR}")
        endforeach()
    elseif(NOT WIN32)
        message(STATUS "verifiers not registered: they run from Windows until stage R.10")
    else()
        message(STATUS "verifiers not registered: no Python 3 found")
    endif()
endif()
