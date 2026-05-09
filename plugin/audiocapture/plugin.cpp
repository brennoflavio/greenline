#include <QQmlExtensionPlugin>
#include <qqml.h>

#include "audiocapturerecorder.h"

class AudioCapturePlugin : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)

public:
    void registerTypes(const char *uri) override
    {
        qmlRegisterType<AudioCaptureRecorder>(uri, 1, 0, "AudioCaptureRecorder");
    }
};

#include "plugin.moc"
