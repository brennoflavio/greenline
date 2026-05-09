#include "audiocapturerecorder.h"

#include <QAudioEncoderSettings>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QMediaRecorder>
#include <QStandardPaths>
#include <QUrl>
#include <QVideoEncoderSettings>

namespace {
QString preferredContainer(const QStringList &supportedContainers)
{
    if (supportedContainers.contains(QStringLiteral("audio/ogg")))
        return QStringLiteral("audio/ogg");

    if (supportedContainers.contains(QStringLiteral("audio/mp4")))
        return QStringLiteral("audio/mp4");

    if (supportedContainers.contains(QStringLiteral("audio/x-wav")))
        return QStringLiteral("audio/x-wav");

    return QString();
}

QString preferredAudioCodec(const QStringList &supportedCodecs)
{
    if (supportedCodecs.contains(QStringLiteral("audio/x-opus")))
        return QStringLiteral("audio/x-opus");

    return QString();
}

QString fileExtensionForContainer(const QString &container)
{
    if (container == QStringLiteral("audio/mp4"))
        return QStringLiteral("m4a");

    if (container == QStringLiteral("audio/x-wav"))
        return QStringLiteral("wav");

    return QStringLiteral("ogg");
}
}

AudioCaptureRecorder::AudioCaptureRecorder(QObject *parent)
    : QObject(parent)
    , m_status(QStringLiteral("unloaded"))
    , m_duration(0)
    , m_readyToSend(false)
    , m_clearOutputPending(false)
    , m_recordingSessionActive(false)
    , m_recordingCompletedPending(false)
{
    configureRecorder();

    connect(&m_recorder, SIGNAL(stateChanged(QMediaRecorder::State)), this, SLOT(handleStateChanged(QMediaRecorder::State)));
    connect(&m_recorder, SIGNAL(statusChanged(QMediaRecorder::Status)), this, SLOT(handleStatusChanged(QMediaRecorder::Status)));
    connect(&m_recorder, SIGNAL(durationChanged(qint64)), this, SLOT(handleDurationChanged(qint64)));
    connect(&m_recorder, SIGNAL(error(QMediaRecorder::Error)), this, SLOT(handleError(QMediaRecorder::Error)));

    setOutputFile(defaultOutputFile());
    m_errorString = voiceNoteSupportError();
    handleStatusChanged(m_recorder.status());
}

QString AudioCaptureRecorder::outputFile() const
{
    return m_outputFile;
}

void AudioCaptureRecorder::setOutputFile(const QString &outputFile)
{
    const QString normalized = normalizeOutputFile(outputFile);
    if (m_outputFile == normalized)
        return;

    m_outputFile = normalized;
    emit outputFileChanged();
}

bool AudioCaptureRecorder::recording() const
{
    return m_recorder.state() == QMediaRecorder::RecordingState;
}

qint64 AudioCaptureRecorder::duration() const
{
    return m_duration;
}

bool AudioCaptureRecorder::readyToSend() const
{
    return m_readyToSend;
}

QString AudioCaptureRecorder::status() const
{
    return m_status;
}

QString AudioCaptureRecorder::errorString() const
{
    return m_errorString;
}

QString AudioCaptureRecorder::defaultOutputFile() const
{
    if (!voiceNoteSupportError().isEmpty())
        return QString();

    QString cachePath = QStandardPaths::writableLocation(QStandardPaths::CacheLocation);
    if (cachePath.isEmpty())
        cachePath = QDir::tempPath();

    const QString container = preferredContainer(m_recorder.supportedContainers());
    const QString extension = fileExtensionForContainer(container);
    const QString fileName = QStringLiteral("audio-capture-%1.%2")
                                 .arg(QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMddHHmmsszzz")))
                                 .arg(extension);
    return QDir(cachePath).filePath(fileName);
}

bool AudioCaptureRecorder::start()
{
    if (recording())
        return true;

    m_clearOutputPending = false;

    const QString supportError = voiceNoteSupportError();
    if (!supportError.isEmpty()) {
        if (m_errorString != supportError) {
            m_errorString = supportError;
            emit errorStringChanged();
        }
        return false;
    }

    if (!m_recorder.isAvailable()) {
        const QString nextError = QStringLiteral("Audio recorder is not available");
        if (m_errorString != nextError) {
            m_errorString = nextError;
            emit errorStringChanged();
        }
        return false;
    }

    if (m_outputFile.isEmpty())
        setOutputFile(defaultOutputFile());

    const QFileInfo outputInfo(m_outputFile);
    QDir outputDir = outputInfo.dir();
    if (!outputDir.exists() && !outputDir.mkpath(QStringLiteral("."))) {
        const QString nextError = QStringLiteral("Could not create output directory");
        if (m_errorString != nextError) {
            m_errorString = nextError;
            emit errorStringChanged();
        }
        return false;
    }

    if (!m_errorString.isEmpty()) {
        m_errorString.clear();
        emit errorStringChanged();
    }

    if (!m_recorder.setOutputLocation(QUrl::fromLocalFile(m_outputFile))) {
        const QString nextError = m_recorder.errorString().isEmpty() ? QStringLiteral("Could not set recorder output location") : m_recorder.errorString();
        m_errorString = nextError;
        emit errorStringChanged();
        return false;
    }

    m_recorder.record();
    if (m_recorder.state() == QMediaRecorder::StoppedState) {
        const QString nextError = m_recorder.errorString().isEmpty() ? QStringLiteral("Could not start audio recording") : m_recorder.errorString();
        m_errorString = nextError;
        emit errorStringChanged();
        return false;
    }

    return true;
}

bool AudioCaptureRecorder::startRecording(const QString &outputFile)
{
    if (!outputFile.isEmpty())
        setOutputFile(outputFile);

    return start();
}

void AudioCaptureRecorder::stop()
{
    if (m_recorder.state() == QMediaRecorder::StoppedState)
        return;

    m_recorder.stop();
}

void AudioCaptureRecorder::clearOutput()
{
    if (recording()) {
        m_clearOutputPending = true;
        stop();
        return;
    }

    if (m_recorder.status() == QMediaRecorder::FinalizingStatus) {
        m_clearOutputPending = true;
        return;
    }

    m_clearOutputPending = false;
    if (!m_outputFile.isEmpty())
        QFile::remove(m_outputFile);

    resetRecordingData();
    setOutputFile(defaultOutputFile());
}

void AudioCaptureRecorder::handleStateChanged(QMediaRecorder::State state)
{
    const QString nextStatus = stateToString(state);
    if (m_status != nextStatus) {
        m_status = nextStatus;
        emit statusChanged();
    }

    if (state == QMediaRecorder::RecordingState) {
        m_recordingSessionActive = true;
        m_recordingCompletedPending = false;
        setDuration(0);
        setReadyToSend(false);
    } else if (state == QMediaRecorder::StoppedState && m_recordingSessionActive) {
        m_recordingCompletedPending = true;
        handleStatusChanged(m_recorder.status());
    }

    emit recordingChanged();
}

void AudioCaptureRecorder::handleStatusChanged(QMediaRecorder::Status status)
{
    const QString nextStatus = statusToString(status);
    if (m_status != nextStatus) {
        m_status = nextStatus;
        emit statusChanged();
    }

    const bool inactiveStatus = status != QMediaRecorder::RecordingStatus
        && status != QMediaRecorder::StartingStatus
        && status != QMediaRecorder::FinalizingStatus;

    if (m_clearOutputPending && inactiveStatus) {
        m_clearOutputPending = false;
        if (!m_outputFile.isEmpty())
            QFile::remove(m_outputFile);
        resetRecordingData();
        setOutputFile(defaultOutputFile());
        return;
    }

    if (m_recordingCompletedPending && inactiveStatus) {
        m_recordingCompletedPending = false;
        m_recordingSessionActive = false;

        const QFileInfo outputInfo(m_outputFile);
        if (outputInfo.exists() && outputInfo.size() > 0) {
            setReadyToSend(true);
            emit recordingReady();
            return;
        }

        const QString nextError = QStringLiteral("Recording did not produce an audio file");
        if (m_errorString != nextError) {
            m_errorString = nextError;
            emit errorStringChanged();
        }
    }
}

void AudioCaptureRecorder::handleDurationChanged(qint64 duration)
{
    setDuration(duration);
}

void AudioCaptureRecorder::handleError(QMediaRecorder::Error error)
{
    Q_UNUSED(error)

    const QString nextError = m_recorder.errorString();
    if (m_errorString == nextError)
        return;

    m_errorString = nextError;
    emit errorStringChanged();
}

void AudioCaptureRecorder::configureRecorder()
{
    QAudioEncoderSettings audioSettings;
    audioSettings.setQuality(QMultimedia::HighQuality);
    audioSettings.setSampleRate(16000);
    audioSettings.setEncodingMode(QMultimedia::ConstantQualityEncoding);
    audioSettings.setChannelCount(1);

    const QString codec = preferredAudioCodec(m_recorder.supportedAudioCodecs());
    if (!codec.isEmpty())
        audioSettings.setCodec(codec);

    const QString container = preferredContainer(m_recorder.supportedContainers());

    m_recorder.setEncodingSettings(audioSettings, QVideoEncoderSettings(), container);
    m_recorder.setVolume(1.0);
}

QString AudioCaptureRecorder::voiceNoteSupportError() const
{
    if (!m_recorder.isAvailable())
        return QStringLiteral("Audio recorder is not available");

    if (preferredContainer(m_recorder.supportedContainers()) != QStringLiteral("audio/ogg"))
        return QStringLiteral("Voice notes require OGG audio recording support on this device");

    if (preferredAudioCodec(m_recorder.supportedAudioCodecs()) != QStringLiteral("audio/x-opus"))
        return QStringLiteral("Voice notes require Opus audio codec support on this device");

    return QString();
}

QString AudioCaptureRecorder::preferredAudioCodec(const QStringList &supportedCodecs)
{
    return ::preferredAudioCodec(supportedCodecs);
}

void AudioCaptureRecorder::setDuration(qint64 duration)
{
    if (m_duration == duration)
        return;

    m_duration = duration;
    emit durationChanged();
}

void AudioCaptureRecorder::setReadyToSend(bool readyToSend)
{
    if (m_readyToSend == readyToSend)
        return;

    m_readyToSend = readyToSend;
    emit readyToSendChanged();
}

void AudioCaptureRecorder::resetRecordingData()
{
    setDuration(0);
    setReadyToSend(false);
    m_recordingSessionActive = false;
    m_recordingCompletedPending = false;
}

QString AudioCaptureRecorder::normalizeOutputFile(const QString &outputFile)
{
    if (outputFile.startsWith(QStringLiteral("file://")))
        return QUrl(outputFile).toLocalFile();

    return outputFile;
}

QString AudioCaptureRecorder::statusToString(QMediaRecorder::Status status)
{
    switch (status) {
    case QMediaRecorder::UnavailableStatus:
        return QStringLiteral("unavailable");
    case QMediaRecorder::UnloadedStatus:
        return QStringLiteral("unloaded");
    case QMediaRecorder::LoadingStatus:
        return QStringLiteral("loading");
    case QMediaRecorder::LoadedStatus:
        return QStringLiteral("loaded");
    case QMediaRecorder::StartingStatus:
        return QStringLiteral("starting");
    case QMediaRecorder::RecordingStatus:
        return QStringLiteral("recording");
    case QMediaRecorder::PausedStatus:
        return QStringLiteral("paused");
    case QMediaRecorder::FinalizingStatus:
        return QStringLiteral("finalizing");
    }

    return QStringLiteral("unknown");
}

QString AudioCaptureRecorder::stateToString(QMediaRecorder::State state)
{
    switch (state) {
    case QMediaRecorder::StoppedState:
        return QStringLiteral("waiting");
    case QMediaRecorder::RecordingState:
        return QStringLiteral("recording");
    case QMediaRecorder::PausedState:
        return QStringLiteral("paused");
    }

    return QStringLiteral("unknown");
}
