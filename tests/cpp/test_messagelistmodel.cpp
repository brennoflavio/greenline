#include "messagelistmodel.h"

#include <QAbstractItemModel>
#include <QTextStream>

namespace {

QVariantMap message(const QString &id, qlonglong timestamp, const QString &tempId = QString(), const QString &text = QString())
{
    QVariantMap value;
    value.insert(QStringLiteral("id"), id);
    value.insert(QStringLiteral("temp_id"), tempId);
    value.insert(QStringLiteral("timestamp_unix"), timestamp);
    value.insert(QStringLiteral("text"), text);
    return value;
}

bool check(bool condition, const QString &description)
{
    if (condition)
        return true;

    QTextStream(stderr) << "FAIL: " << description << '\n';
    return false;
}

}

int main()
{
    int failures = 0;
    MessageListModel model;

    model.resetMessages(QVariantList() << message(QStringLiteral("old"), 1) << message(QStringLiteral("new"), 2));
    failures += !check(model.count() == 2, QStringLiteral("reset sets count"));
    failures += !check(model.messageAt(0).value(QStringLiteral("id")) == QStringLiteral("new"), QStringLiteral("reset stores newest first"));

    int insertSignalCount = 0;
    int insertedFirst = -1;
    int insertedLast = -1;
    QObject::connect(
        &model,
        &QAbstractItemModel::rowsInserted,
        [&insertSignalCount, &insertedFirst, &insertedLast](const QModelIndex &, int first, int last) {
            ++insertSignalCount;
            insertedFirst = first;
            insertedLast = last;
        });

    const QVariantList inserted = model.upsertMessages(
        QVariantList() << message(QStringLiteral("newest-1"), 3) << message(QStringLiteral("newest-2"), 4));
    failures += !check(inserted.size() == 2, QStringLiteral("upsert reports inserted messages"));
    failures += !check(insertSignalCount == 1 && insertedFirst == 0 && insertedLast == 1, QStringLiteral("newest burst is one row insertion"));
    failures += !check(model.messageAt(0).value(QStringLiteral("id")) == QStringLiteral("newest-2"), QStringLiteral("burst remains sorted"));

    int dataChangedCount = 0;
    QObject::connect(
        &model,
        &QAbstractItemModel::dataChanged,
        [&dataChangedCount](const QModelIndex &, const QModelIndex &, const QVector<int> &) {
            ++dataChangedCount;
        });
    insertSignalCount = 0;
    model.upsertMessages(QVariantList() << message(QStringLiteral("newest-2"), 4, QString(), QStringLiteral("updated")));
    failures += !check(insertSignalCount == 0 && dataChangedCount == 1, QStringLiteral("same-position update preserves its row"));

    model.resetMessages(QVariantList() << message(QStringLiteral("pending-1"), 5, QStringLiteral("pending-1"), QStringLiteral("pending")));
    const QVariantList reconciled = model.upsertMessages(
        QVariantList()
        << message(QStringLiteral("server-1"), 5, QStringLiteral("pending-1"), QStringLiteral("sent"))
        << message(QStringLiteral("server-1"), 5, QString(), QStringLiteral("delivered")));
    failures += !check(reconciled.isEmpty(), QStringLiteral("pending transition updates instead of inserting"));
    failures += !check(model.count() == 1, QStringLiteral("pending transition does not duplicate rows"));
    failures += !check(model.messageAt(0).value(QStringLiteral("id")) == QStringLiteral("server-1"), QStringLiteral("pending transition keeps server id"));
    failures += !check(model.messageAt(0).value(QStringLiteral("temp_id")) == QStringLiteral("pending-1"), QStringLiteral("pending transition preserves alias"));
    failures += !check(model.messageAt(0).value(QStringLiteral("text")) == QStringLiteral("delivered"), QStringLiteral("pending transition keeps final state"));

    int moveSignalCount = 0;
    QObject::connect(
        &model,
        &QAbstractItemModel::rowsMoved,
        [&moveSignalCount](const QModelIndex &, int, int, const QModelIndex &, int) {
            ++moveSignalCount;
        });
    model.resetMessages(QVariantList() << message(QStringLiteral("move-me"), 1) << message(QStringLiteral("stay"), 2));
    model.upsertMessages(QVariantList() << message(QStringLiteral("move-me"), 3));
    failures += !check(moveSignalCount == 1, QStringLiteral("timestamp update moves the existing row"));
    failures += !check(model.messageAt(0).value(QStringLiteral("id")) == QStringLiteral("move-me"), QStringLiteral("moved row reaches sorted position"));

    return failures == 0 ? 0 : 1;
}
