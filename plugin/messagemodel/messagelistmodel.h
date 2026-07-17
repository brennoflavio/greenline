#ifndef MESSAGELISTMODEL_H
#define MESSAGELISTMODEL_H

#include <QAbstractListModel>
#include <QHash>
#include <QVariantList>
#include <QVariantMap>
#include <QVector>

class MessageListModel : public QAbstractListModel
{
    Q_OBJECT
    Q_PROPERTY(int count READ count NOTIFY countChanged)

public:
    enum MessageRoles {
        MessageRole = Qt::UserRole + 1,
    };
    Q_ENUM(MessageRoles)

    explicit MessageListModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;

    int count() const;

    Q_INVOKABLE void clear();
    Q_INVOKABLE void resetMessages(const QVariantList &oldestFirstMessages);
    Q_INVOKABLE QVariantList upsertMessages(const QVariantList &messages);
    Q_INVOKABLE QVariantList appendOlderMessages(const QVariantList &oldestFirstMessages);
    Q_INVOKABLE bool patchMessage(const QString &messageId, const QString &tempId, const QVariantMap &patch);
    Q_INVOKABLE int indexOfMessage(const QString &messageId) const;
    Q_INVOKABLE bool containsMessage(const QString &messageId) const;
    Q_INVOKABLE QVariantMap messageAt(int index) const;
    Q_INVOKABLE QVariantList messagesOldestFirst() const;

signals:
    void countChanged();

private:
    static QString messageId(const QVariantMap &message);
    static QString tempId(const QVariantMap &message);
    static QString sortId(const QVariantMap &message);
    static qlonglong timestamp(const QVariantMap &message);
    static bool displayBefore(const QVariantMap &left, const QVariantMap &right);
    static QVector<QVariantMap> normalizedMessages(const QVariantList &messages);

    int findMessageIndex(const QVariantMap &message) const;
    int displayInsertIndex(const QVariantMap &message, const QVector<QVariantMap> &messages) const;
    void rebuildIndexes();
    void replaceAliases(int index, const QVariantMap &previous, const QVariantMap &message);
    void updateMessageAt(int index, const QVariantMap &message);
    void insertNewMessages(QVector<QVariantMap> messages);

    QVector<QVariantMap> m_messages;
    QHash<QString, int> m_indexesByAlias;
};

#endif
