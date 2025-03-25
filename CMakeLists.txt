# SPDX-FileCopyrightText: 2023-2025 KerJoe <2002morozik@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

cmake_minimum_required(VERSION 3.16)

set(PROJECT_VERSION "2.0")
project(ksystemstats_scripts VERSION ${PROJECT_VERSION})

set(KSYSGUARD_MIN_VERSION "6.2.90")
set(QT_MIN_VERSION "6.7.0")
set(KF6_MIN_VERSION "6.10.0")
set(KDE_COMPILERSETTINGS_LEVEL "5.82")

find_package(ECM ${KF6_MIN_VERSION} REQUIRED NO_MODULE)
set(CMAKE_MODULE_PATH ${ECM_MODULE_PATH}  ${CMAKE_CURRENT_SOURCE_DIR}/cmake)
set(QT_MAJOR_VERSION 6) # ?

include(KDEInstallDirs)
include(KDECMakeSettings)
include(KDECompilerSettings NO_POLICY_SCOPE)

find_package(Qt6 ${QT_MIN_VERSION} CONFIG REQUIRED COMPONENTS Core)
find_package(KF6 ${KF6_MIN_VERSION} REQUIRED COMPONENTS CoreAddons I18n)
find_package(KSysGuard ${KSYSGUARD_MIN_VERSION} REQUIRED)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

set(KSYSTEMSTATS_PLUGIN_INSTALL_DIR ${KDE_INSTALL_PLUGINDIR}/ksystemstats)

add_library(ksystemstats_plugin_scripts MODULE scripts.cpp)
if(NOT (CMAKE_BUILD_TYPE STREQUAL "Debug"))
    target_compile_definitions(ksystemstats_plugin_scripts PUBLIC -DQT_NO_DEBUG_OUTPUT)
endif()

target_link_libraries(ksystemstats_plugin_scripts Qt::Core KF6::CoreAddons KF6::I18n KSysGuard::SystemStats)
install(TARGETS ksystemstats_plugin_scripts DESTINATION ${KSYSTEMSTATS_PLUGIN_INSTALL_DIR})

feature_summary(WHAT ALL INCLUDE_QUIET_PACKAGES FATAL_ON_MISSING_REQUIRED_PACKAGES)
