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
#include <QStandardPaths>
#include <QDir>

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

class Script;

struct Request
{
  std::coroutine_handle<> *hp; Script* script;
  Request* request(QString request0, QString request1="");

  constexpr bool await_ready() const noexcept { return false; }
  void await_suspend(std::coroutine_handle<> h) { *hp = h; }
  QString await_resume() noexcept;
};

class Script : public KSysGuard::SensorObject
{
    Q_OBJECT

    friend Request;

public:
    Script(const QString &scriptPath, const QString &scriptName, KSysGuard::SensorContainer *parent);
    void update();
private:
    Coroutine initSensors(std::coroutine_handle<> *h);
    Coroutine updateSensors(std::coroutine_handle<> *h);
    QProcess scriptProcess;
    QString name;
    QString scriptReply;
    QList<KSysGuard::SensorProperty*> sensors;
    std::coroutine_handle<> initSensorsH, updateSensorsH;
    bool initialized = false, updateFinished = true;
private slots:
    void readyReadStandardOutput();
    void stateChanged(QProcess::ProcessState newState);
};

class ScriptsPlugin : public KSysGuard::SensorPlugin
{
    Q_OBJECT

public:
    ScriptsPlugin(QObject *parent, const QVariantList &args);
    QString providerName() const override
    {
        return QStringLiteral("scripts");
    };

    void update() override;

private:
    KSysGuard::SensorContainer *container;
    QHash<QString, Script*> scripts;
};

#endif
