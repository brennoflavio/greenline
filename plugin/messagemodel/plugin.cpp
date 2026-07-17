#include <QQmlExtensionPlugin>
#include <qqml.h>

#include "messagelistmodel.h"

class MessageModelPlugin : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)

public:
    void registerTypes(const char *uri) override
    {
        qmlRegisterType<MessageListModel>(uri, 1, 0, "MessageListModel");
    }
};

#include "plugin.moc"
