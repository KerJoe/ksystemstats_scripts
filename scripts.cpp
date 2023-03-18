/*
    SPDX-FileCopyrightText: 2023 Mikhail Morozov <2002morozik@gmail.com>

    SPDX-License-Identifier: GPL-2.0-only OR GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "scripts.h"
#include <qalgorithms.h>
#include <qfileinfo.h>
#include <qfilesystemwatcher.h>

K_PLUGIN_CLASS_WITH_JSON(ScriptsPlugin, "metadata.json")

Request* Request::request(QString request0, QString request1)
{
    qDebug() << "Requested:" << request0 + (request1 == "" ? QString("") : "\t" + request1);
    script->scriptProcess.write((request0 + (request1 == "" ? QString("") : "\t" + request1) + "\n").toLocal8Bit());
    return this;
}

QString Request::await_resume() noexcept
{
    return script->scriptReply;
}

Script::Script(const QString &scriptPath, const QString &scriptRelPath, const QString &scriptName, KSysGuard::SensorContainer *parent) : KSysGuard::SensorObject(scriptRelPath, scriptName, parent)
{
    name = scriptName;
    qDebug() << "Script:" << scriptName << "Path:" << scriptPath;

    auto n = new KSysGuard::SensorProperty("name", i18nc("@title", "Name"), name, this);
    n->setVariantType(QVariant::String);

    connect(&scriptProcess, &QProcess::readyReadStandardOutput, this, &Script::readyReadStandardOutput);
    connect(&scriptProcess, &QProcess::stateChanged, this, &Script::stateChanged);
    scriptProcess.start(scriptPath, {});
}

void Script::readyReadStandardOutput()
{
    scriptReply = scriptProcess.readAll().trimmed();
    qDebug() << "Recieved: " << scriptReply;
    if (!initialized)
        initSensorsH();
    else if (!updateFinished)
        updateSensorsH();
}

void Script::stateChanged(QProcess::ProcessState newState)
{
    qDebug() << "Script:" << name << "State:" << newState;
    if (newState == QProcess::ProcessState::Running)
        initSensors(&initSensorsH);
}

void Script::update()
{
    if (updateFinished)
        updateSensors(&updateSensorsH);
}

Coroutine Script::updateSensors(std::coroutine_handle<> *h)
{
    updateFinished = false;

    Request r{h, this};
    for (auto& sensor : qAsConst(sensors))
        sensor->setValue(QVariant(co_await *r.request(sensor->id(), "value")));

    updateFinished = true;
}

Coroutine Script::initSensors(std::coroutine_handle<> *h)
{
    Request r{h, this};

    QMap<QString, QString> sensorParameters
    {
        { "initial_value", "" },
        { "name", "" },
        { "short_name", "" },
        { "prefix", "" },
        { "description", "" },
        { "min", "" },
        { "max", "" },
        { "unit", "" },
        { "variant_type", "" },
    };
    const QMap<QString, KSysGuard::Unit> Str2Unit
    {
        { "-", KSysGuard::UnitNone },
        { "B", KSysGuard::UnitByte },
        { "B/s", KSysGuard::UnitByteRate },
        { "Hz", KSysGuard::UnitHertz },
        { "Timestamp", KSysGuard::UnitBootTimestamp },
        { "s", KSysGuard::UnitSecond },
        { "Time", KSysGuard::UnitTime },
        { "Ticks", KSysGuard::UnitTicks },
        { "C", KSysGuard::UnitCelsius },
        { "b/s", KSysGuard::UnitBitRate },
        { "dBm", KSysGuard::UnitDecibelMilliWatts },
        { "%", KSysGuard::UnitPercent },
        { "rate", KSysGuard::UnitRate },
        { "rpm", KSysGuard::UnitRpm },
        { "V", KSysGuard::UnitVolt },
        { "W", KSysGuard::UnitWatt },
        { "Wh", KSysGuard::UnitWattHour },
        { "A", KSysGuard::UnitAmpere },
    };

    auto sensorNames = (co_await *r.request("?")).split("\t");
    qDebug() << sensorNames;
    for (const auto& sensorName : qAsConst(sensorNames))
    {
        for (const auto& sensorParameter : sensorParameters.keys())
            sensorParameters[sensorParameter] = co_await *r.request(sensorName, sensorParameter);

        auto sensor = new KSysGuard::SensorProperty(
            sensorName,
            sensorParameters["name"] == "" ? sensorName : sensorParameters["name"],
            QVariant(sensorParameters["initial_value"]),
            this);
        if (sensorParameters["short_name"] != "") sensor->setShortName(sensorParameters["short_name"]);
        if (sensorParameters["prefix"] != "") sensor->setPrefix(sensorParameters["prefix"]);
        if (sensorParameters["description"] != "") sensor->setDescription(sensorParameters["description"]);
        if (sensorParameters["min"] != "") sensor->setMin(sensorParameters["min"].toDouble());
        if (sensorParameters["max"] != "") sensor->setMax(sensorParameters["max"].toDouble());
        if (sensorParameters["variant_type"] != "" ) sensor->setVariantType(
            QVariant::nameToType(sensorParameters["variant_type"].toLocal8Bit().constData()));
        if (sensorParameters["unit"] != "")
        {
            auto unit = KSysGuard::UnitInvalid;
            if (Str2Unit.contains(sensorParameters["unit"]))
                unit = Str2Unit[sensorParameters["unit"]];
            sensor->setUnit(unit);
        }

        sensors.append(sensor);
    }
    initialized = true;
}

ScriptsPlugin::ScriptsPlugin(QObject *parent, const QVariantList &args) : SensorPlugin(parent, args)
{
    container = new KSysGuard::SensorContainer("scripts", i18nc("@title", "Scripts"), this);

    scriptDirWatcher.addPath(scriptDirPath);
    connect(&scriptDirWatcher, &QFileSystemWatcher::directoryChanged, this, &ScriptsPlugin::directoryChanged);

    initScripts();
}

void ScriptsPlugin::initScripts()
{
    auto scriptPathItr = QDirIterator(scriptDirPath, QDir::NoDotAndDotDot | QDir::Files, QDirIterator::Subdirectories);
    while (scriptPathItr.hasNext())
    {
        auto scriptAbsPath = scriptPathItr.next();
        auto scriptRelPath = QDir(scriptDirPath).relativeFilePath(scriptAbsPath);
        auto scriptName = QFileInfo(scriptAbsPath).fileName();
        scripts.insert(scriptRelPath, new Script(scriptAbsPath, scriptRelPath, scriptName, container));
    }
}

void ScriptsPlugin::deinitScripts()
{
    qDeleteAll(scripts.begin(), scripts.end());
    scripts.clear();
}

void ScriptsPlugin::update()
{
    qDebug() << "Update called";
    for (auto& script : qAsConst(scripts))
        script->update();
}

void ScriptsPlugin::directoryChanged(const QString& path)
{
    Q_UNUSED(path)

    qDebug() << "Directory changed";

    deinitScripts();
    initScripts();
}

#include "scripts.moc"
