#include "messagelistmodel.h"

#include <algorithm>

MessageListModel::MessageListModel(QObject *parent)
    : QAbstractListModel(parent)
{
}

int MessageListModel::rowCount(const QModelIndex &parent) const
{
    if (parent.isValid())
        return 0;

    return m_messages.size();
}

QVariant MessageListModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_messages.size())
        return QVariant();

    if (role == MessageRole)
        return m_messages.at(index.row());

    return QVariant();
}

QHash<int, QByteArray> MessageListModel::roleNames() const
{
    QHash<int, QByteArray> roles;
    roles.insert(MessageRole, "message");
    return roles;
}

int MessageListModel::count() const
{
    return m_messages.size();
}

void MessageListModel::clear()
{
    if (m_messages.isEmpty())
        return;

    beginResetModel();
    m_messages.clear();
    m_indexesByAlias.clear();
    endResetModel();
    emit countChanged();
}

void MessageListModel::resetMessages(const QVariantList &oldestFirstMessages)
{
    QVector<QVariantMap> nextMessages = normalizedMessages(oldestFirstMessages);
    std::sort(nextMessages.begin(), nextMessages.end(), displayBefore);

    const int previousCount = m_messages.size();
    beginResetModel();
    m_messages = nextMessages;
    rebuildIndexes();
    endResetModel();

    if (previousCount != m_messages.size())
        emit countChanged();
}

QVariantList MessageListModel::upsertMessages(const QVariantList &messages)
{
    const QVector<QVariantMap> normalized = normalizedMessages(messages);
    QVector<QVariantMap> newMessages;
    QVariantList insertedMessages;

    for (const QVariantMap &message : normalized) {
        const int existingIndex = findMessageIndex(message);
        if (existingIndex >= 0) {
            updateMessageAt(existingIndex, message);
            continue;
        }

        newMessages.append(message);
        insertedMessages.append(message);
    }

    if (!newMessages.isEmpty()) {
        insertNewMessages(newMessages);
        emit countChanged();
    }

    return insertedMessages;
}

QVariantList MessageListModel::appendOlderMessages(const QVariantList &oldestFirstMessages)
{
    return upsertMessages(oldestFirstMessages);
}

bool MessageListModel::patchMessage(const QString &messageIdValue, const QString &tempIdValue, const QVariantMap &patch)
{
    QVariantMap lookup;
    lookup.insert(QStringLiteral("id"), messageIdValue);
    lookup.insert(QStringLiteral("temp_id"), tempIdValue);
    const int index = findMessageIndex(lookup);
    if (index < 0)
        return false;

    QVariantMap message = m_messages.at(index);
    bool changed = false;
    for (auto it = patch.constBegin(); it != patch.constEnd(); ++it) {
        if (message.value(it.key()) == it.value())
            continue;

        message.insert(it.key(), it.value());
        changed = true;
    }
    if (!changed)
        return false;

    updateMessageAt(index, message);
    return true;
}

int MessageListModel::indexOfMessage(const QString &messageIdValue) const
{
    if (messageIdValue.isEmpty())
        return -1;

    return m_indexesByAlias.value(messageIdValue, -1);
}

bool MessageListModel::containsMessage(const QString &messageIdValue) const
{
    return indexOfMessage(messageIdValue) >= 0;
}

QVariantMap MessageListModel::messageAt(int index) const
{
    if (index < 0 || index >= m_messages.size())
        return QVariantMap();

    return m_messages.at(index);
}

QVariantList MessageListModel::messagesOldestFirst() const
{
    QVariantList messages;
    messages.reserve(m_messages.size());
    for (auto it = m_messages.crbegin(); it != m_messages.crend(); ++it)
        messages.append(*it);

    return messages;
}

QString MessageListModel::messageId(const QVariantMap &message)
{
    return message.value(QStringLiteral("id")).toString();
}

QString MessageListModel::tempId(const QVariantMap &message)
{
    return message.value(QStringLiteral("temp_id")).toString();
}

QString MessageListModel::sortId(const QVariantMap &message)
{
    const QString id = messageId(message);
    return id.isEmpty() ? tempId(message) : id;
}

qlonglong MessageListModel::timestamp(const QVariantMap &message)
{
    return message.value(QStringLiteral("timestamp_unix")).toLongLong();
}

bool MessageListModel::displayBefore(const QVariantMap &left, const QVariantMap &right)
{
    const qlonglong leftTimestamp = timestamp(left);
    const qlonglong rightTimestamp = timestamp(right);
    if (leftTimestamp != rightTimestamp)
        return leftTimestamp > rightTimestamp;

    return sortId(left) > sortId(right);
}

QVector<QVariantMap> MessageListModel::normalizedMessages(const QVariantList &messages)
{
    QVector<QVariantMap> normalized;
    QHash<QString, int> indexesByAlias;

    for (const QVariant &value : messages) {
        QVariantMap message = value.toMap();
        if (message.isEmpty())
            continue;

        const QString id = messageId(message);
        QString temporaryId = tempId(message);
        int existingIndex = -1;
        if (!id.isEmpty())
            existingIndex = indexesByAlias.value(id, -1);
        if (existingIndex < 0 && !temporaryId.isEmpty())
            existingIndex = indexesByAlias.value(temporaryId, -1);

        if (existingIndex < 0) {
            existingIndex = normalized.size();
            normalized.append(message);
        } else {
            const QVariantMap previous = normalized.at(existingIndex);
            const QString previousId = messageId(previous);
            const QString previousTempId = tempId(previous);
            if (temporaryId.isEmpty() && !previousTempId.isEmpty()) {
                message.insert(QStringLiteral("temp_id"), previousTempId);
                temporaryId = previousTempId;
            }
            if (!previousId.isEmpty() && indexesByAlias.value(previousId, -1) == existingIndex)
                indexesByAlias.remove(previousId);
            if (!previousTempId.isEmpty() && indexesByAlias.value(previousTempId, -1) == existingIndex)
                indexesByAlias.remove(previousTempId);
            normalized[existingIndex] = message;
        }

        if (!id.isEmpty())
            indexesByAlias.insert(id, existingIndex);
        if (!temporaryId.isEmpty())
            indexesByAlias.insert(temporaryId, existingIndex);
    }

    return normalized;
}

int MessageListModel::findMessageIndex(const QVariantMap &message) const
{
    const QString id = messageId(message);
    if (!id.isEmpty() && m_indexesByAlias.contains(id))
        return m_indexesByAlias.value(id);

    const QString temporaryId = tempId(message);
    if (!temporaryId.isEmpty() && m_indexesByAlias.contains(temporaryId))
        return m_indexesByAlias.value(temporaryId);

    return -1;
}

int MessageListModel::displayInsertIndex(const QVariantMap &message, const QVector<QVariantMap> &messages) const
{
    int low = 0;
    int high = messages.size();
    while (low < high) {
        const int middle = low + (high - low) / 2;
        if (displayBefore(message, messages.at(middle)))
            high = middle;
        else
            low = middle + 1;
    }
    return low;
}

void MessageListModel::rebuildIndexes()
{
    m_indexesByAlias.clear();
    for (int index = 0; index < m_messages.size(); ++index) {
        const QVariantMap &message = m_messages.at(index);
        const QString id = messageId(message);
        const QString temporaryId = tempId(message);
        if (!id.isEmpty())
            m_indexesByAlias.insert(id, index);
        if (!temporaryId.isEmpty())
            m_indexesByAlias.insert(temporaryId, index);
    }
}

void MessageListModel::replaceAliases(int index, const QVariantMap &previous, const QVariantMap &message)
{
    const QString previousId = messageId(previous);
    const QString previousTempId = tempId(previous);
    if (!previousId.isEmpty() && m_indexesByAlias.value(previousId, -1) == index)
        m_indexesByAlias.remove(previousId);
    if (!previousTempId.isEmpty() && m_indexesByAlias.value(previousTempId, -1) == index)
        m_indexesByAlias.remove(previousTempId);

    const QString id = messageId(message);
    const QString temporaryId = tempId(message);
    if (!id.isEmpty())
        m_indexesByAlias.insert(id, index);
    if (!temporaryId.isEmpty())
        m_indexesByAlias.insert(temporaryId, index);
}

void MessageListModel::updateMessageAt(int index, const QVariantMap &message)
{
    if (index < 0 || index >= m_messages.size() || m_messages.at(index) == message)
        return;

    const QVariantMap previous = m_messages.at(index);
    QVector<QVariantMap> remaining = m_messages;
    remaining.removeAt(index);
    const int destination = displayInsertIndex(message, remaining);

    if (destination == index) {
        m_messages[index] = message;
        replaceAliases(index, previous, message);
        emit dataChanged(this->index(index, 0), this->index(index, 0), QVector<int>() << MessageRole);
        return;
    }

    const int destinationChild = destination > index ? destination + 1 : destination;
    beginMoveRows(QModelIndex(), index, index, QModelIndex(), destinationChild);
    m_messages[index] = message;
    m_messages.move(index, destination);
    endMoveRows();
    rebuildIndexes();
    emit dataChanged(this->index(destination, 0), this->index(destination, 0), QVector<int>() << MessageRole);
}

void MessageListModel::insertNewMessages(QVector<QVariantMap> messages)
{
    std::sort(messages.begin(), messages.end(), displayBefore);
    if (messages.isEmpty())
        return;

    if (m_messages.isEmpty() || displayBefore(messages.constLast(), m_messages.constFirst())) {
        beginInsertRows(QModelIndex(), 0, messages.size() - 1);
        for (int index = messages.size() - 1; index >= 0; --index)
            m_messages.prepend(messages.at(index));
        endInsertRows();
        rebuildIndexes();
        return;
    }

    if (displayBefore(m_messages.constLast(), messages.constFirst())) {
        const int first = m_messages.size();
        beginInsertRows(QModelIndex(), first, first + messages.size() - 1);
        for (const QVariantMap &message : messages)
            m_messages.append(message);
        endInsertRows();
        rebuildIndexes();
        return;
    }

    for (const QVariantMap &message : messages) {
        const int index = displayInsertIndex(message, m_messages);
        beginInsertRows(QModelIndex(), index, index);
        m_messages.insert(index, message);
        endInsertRows();
    }
    rebuildIndexes();
}
