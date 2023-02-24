/*
    SPDX-FileCopyrightText: 2023 Mikhail Morozov <2002morozik@gmail.com>

    SPDX-License-Identifier: GPL-2.0-only OR GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "scripts.h"

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

Script::Script(const QString &scriptPath, const QString &scriptName, KSysGuard::SensorContainer *parent) : KSysGuard::SensorObject(scriptName, scriptName, parent)
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
        { "variant_type", "" },
        { "unit", "" },
    };
    const QMap<QString, KSysGuard::MetricPrefix> Str2Prefix
    {
        { "-", KSysGuard::MetricPrefixUnity },
        { "K", KSysGuard::MetricPrefixKilo },
        { "M", KSysGuard::MetricPrefixMega },
        { "G", KSysGuard::MetricPrefixGiga },
        { "T", KSysGuard::MetricPrefixTera },
        { "P", KSysGuard::MetricPrefixPeta },
        { "!", KSysGuard::MetricPrefixAutoAdjust },
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
        { "Rate", KSysGuard::UnitRate },
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
            auto unitPrefix = KSysGuard::MetricPrefixAutoAdjust;
            if (Str2Prefix.contains(sensorParameters["unit"].left(1)))
                unitPrefix = Str2Prefix[sensorParameters["unit"].left(1)];

            auto unit = KSysGuard::UnitInvalid;
            if (Str2Unit.contains(sensorParameters["unit"].mid(1)))
                unit = Str2Unit[sensorParameters["unit"].mid(1)];

            sensor->setUnit((KSysGuard::Unit)((int)unitPrefix + (int)unit));
        }

        sensors.append(sensor);
    }
    initialized = true;
}

ScriptsPlugin::ScriptsPlugin(QObject *parent, const QVariantList &args) : SensorPlugin(parent, args)
{
    container = new KSysGuard::SensorContainer("scripts", i18nc("@title", "Scripts"), this);

    auto scriptDirPaths = QStandardPaths::locateAll(QStandardPaths::GenericDataLocation, QStringLiteral("kssscripts"), QStandardPaths::LocateDirectory);
    for (const auto& scriptDirPath : qAsConst(scriptDirPaths))
    {
        auto scriptPaths = QDir(scriptDirPath).entryList(QDir::NoDotAndDotDot | QDir::Files); // TODO: Recursive dirs
        for (const auto& scriptFileName : qAsConst(scriptPaths))
        {
            auto scriptPath = QDir(scriptDirPath).filePath(scriptFileName);
            auto script = new Script(scriptPath, scriptFileName, container);
            scripts.insert(scriptFileName, script);
        }
    }
}

void ScriptsPlugin::update()
{
    qDebug() << "Update called";
    for (auto& script : qAsConst(scripts))
        script->update();
}

#include "scripts.moc"
