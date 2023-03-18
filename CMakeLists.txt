# SPDX-License-Identifier: BSD-2-Clause
# SPDX-FileCopyrightText: 2023 Mikhail Morozov <2002morozik@gmail.com>

cmake_minimum_required(VERSION 3.16)

project(ksystemstats_scripts)
set(PROJECT_VERSION "5.27.80")

set(QT_MIN_VERSION "5.15.2")
set(KF5_MIN_VERSION "5.102.0")
set(KDE_COMPILERSETTINGS_LEVEL "5.82")

find_package(ECM ${KF5_MIN_VERSION} REQUIRED NO_MODULE)
set(CMAKE_MODULE_PATH ${ECM_MODULE_PATH})

include(CheckIncludeFiles)
include(KDEInstallDirs)
include(KDECMakeSettings)
include(KDECompilerSettings NO_POLICY_SCOPE)
include(KDEClangFormat)
include(FeatureSummary)
include(ECMDeprecationSettings)

find_package(Qt${QT_MAJOR_VERSION} ${QT_MIN_VERSION} CONFIG REQUIRED COMPONENTS Core)
find_package(KF5 ${KF5_MIN_VERSION} REQUIRED COMPONENTS CoreAddons)
find_package(KSysGuard REQUIRED)

ecm_set_disabled_deprecation_versions(
    QT 5.15.2
    KF 5.101
)


set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

set(KSYSTEMSTATS_PLUGIN_INSTALL_DIR ${KDE_INSTALL_PLUGINDIR}/ksystemstats)

add_library(ksystemstats_plugin_scripts MODULE scripts.cpp)
if(NOT (CMAKE_BUILD_TYPE STREQUAL "Debug"))
    target_compile_definitions(ksystemstats_plugin_scripts PUBLIC -DQT_NO_DEBUG_OUTPUT)
endif()

target_link_libraries(ksystemstats_plugin_scripts KF5::CoreAddons KF5::I18n KSysGuard::SystemStats)
install(TARGETS ksystemstats_plugin_scripts DESTINATION ${KSYSTEMSTATS_PLUGIN_INSTALL_DIR})

feature_summary(WHAT ALL INCLUDE_QUIET_PACKAGES FATAL_ON_MISSING_REQUIRED_PACKAGES)
