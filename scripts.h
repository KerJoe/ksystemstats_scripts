/*
    SPDX-FileCopyrightText: 2023 Mikhail Morozov <2002morozik@gmail.com>

    SPDX-License-Identifier: GPL-2.0-only OR GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#ifndef SCRIPTS_H
#define SCRIPTS_H

#include <KLocalizedString>
#include <KPluginFactory>

#include <systemstats/AggregateSensor.h>
#include <systemstats/SensorContainer.h>
#include <systemstats/SensorObject.h>
#include <systemstats/SensorProperty.h>

#include <coroutine>

#include <QProcess>
#include <QDir>
#include <QFileSystemWatcher>
#include <QDirIterator>


class Script;


class ScriptsPlugin : public KSysGuard::SensorPlugin
{
    Q_OBJECT

public:
    ScriptsPlugin(QObject *parent, const QVariantList &args);

    const QString scriptDirPath = QDir::homePath() + "/.local/share/ksystemstats-scripts";

    QString providerName() const override { return "scripts"; };
    void update() override;

private:
    KSysGuard::SensorContainer *container;
    QHash<QString, Script*> scripts;
    QFileSystemWatcher scriptDirWatcher;

    void initScripts();
    void deinitScripts();

private slots:
    void directoryChanged(const QString& path);
};


struct Coroutine;
struct Request;

class Script : public KSysGuard::SensorObject
{
    Q_OBJECT

    friend Request;

public:
    Script(const QString &scriptPath, const QString &scriptRelPath, const QString &scriptName, KSysGuard::SensorContainer *parent);
    ~Script();

    void update();
    void restart();
    bool waitInit();

private:
    QProcess scriptProcess;
    QList<KSysGuard::SensorProperty*> sensors;
    QString scriptPath;

    QString scriptReply;

    Coroutine initSensors(std::coroutine_handle<> *h);
    Coroutine updateSensors(std::coroutine_handle<> *h);
    std::coroutine_handle<> initSensorsH, updateSensorsH;
    bool initSensorAct = false, updateSensorsAct = false;

private slots:
    void stateChanged(QProcess::ProcessState newState);
    void readyReadStandardOutput();
};


struct Request
{
  std::coroutine_handle<> *hp;
  Script* script;
  Request* request(QString request0, QString request1="");

  constexpr bool await_ready() const noexcept { return false; }
  void await_suspend(std::coroutine_handle<> h) { *hp = h; }
  QString await_resume() noexcept;
};

struct Coroutine
{
  struct promise_type
  {
    Coroutine get_return_object() { return {}; }
    std::suspend_never initial_suspend() { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() { }
    void unhandled_exception() {}
  };
};

#endif
