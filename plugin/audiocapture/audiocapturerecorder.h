#ifndef AUDIOCAPTURERECORDER_H
#define AUDIOCAPTURERECORDER_H

#include <QAudioRecorder>
#include <QObject>

class AudioCaptureRecorder : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString outputFile READ outputFile WRITE setOutputFile NOTIFY outputFileChanged)
    Q_PROPERTY(bool recording READ recording NOTIFY recordingChanged)
    Q_PROPERTY(qint64 duration READ duration NOTIFY durationChanged)
    Q_PROPERTY(bool readyToSend READ readyToSend NOTIFY readyToSendChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString errorString READ errorString NOTIFY errorStringChanged)

public:
    explicit AudioCaptureRecorder(QObject *parent = nullptr);

    QString outputFile() const;
    void setOutputFile(const QString &outputFile);

    bool recording() const;
    qint64 duration() const;
    bool readyToSend() const;
    QString status() const;
    QString errorString() const;

    Q_INVOKABLE QString defaultOutputFile() const;
    Q_INVOKABLE bool start();
    Q_INVOKABLE bool startRecording(const QString &outputFile);
    Q_INVOKABLE void stop();
    Q_INVOKABLE void clearOutput();

signals:
    void outputFileChanged();
    void recordingChanged();
    void durationChanged();
    void readyToSendChanged();
    void statusChanged();
    void errorStringChanged();
    void recordingReady();

private slots:
    void handleStateChanged(QMediaRecorder::State state);
    void handleStatusChanged(QMediaRecorder::Status status);
    void handleDurationChanged(qint64 duration);
    void handleError(QMediaRecorder::Error error);

private:
    void configureRecorder();
    QString voiceNoteSupportError() const;
    void setDuration(qint64 duration);
    void setReadyToSend(bool readyToSend);
    void resetRecordingData();
    static QString preferredAudioCodec(const QStringList &supportedCodecs);
    static QString normalizeOutputFile(const QString &outputFile);
    static QString statusToString(QMediaRecorder::Status status);
    static QString stateToString(QMediaRecorder::State state);

    QAudioRecorder m_recorder;
    QString m_outputFile;
    QString m_status;
    QString m_errorString;
    qint64 m_duration;
    bool m_readyToSend;
    bool m_clearOutputPending;
    bool m_recordingSessionActive;
    bool m_recordingCompletedPending;
};

#endif
