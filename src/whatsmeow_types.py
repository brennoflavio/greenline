from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MsgBotInfo:
    EditType: str = ""
    EditTargetID: str = ""
    EditSenderTimestampMS: str = ""


@dataclass
class MsgMetaInfo:
    TargetID: str = ""
    TargetSender: str = ""
    TargetChat: str = ""
    DeprecatedLIDSession: Optional[object] = None
    ThreadMessageID: str = ""
    ThreadMessageSenderJID: str = ""


@dataclass
class VerifiedNameCertificate:
    details: str = ""
    signature: str = ""


@dataclass
class VerifiedNameDetails:
    serial: int = 0
    issuer: str = ""
    verifiedName: str = ""


@dataclass
class VerifiedName:
    Certificate: Optional[VerifiedNameCertificate] = None
    Details: Optional[VerifiedNameDetails] = None


@dataclass
class MessageInfo:
    Chat: str = ""
    Sender: str = ""
    IsFromMe: bool = False
    IsGroup: bool = False
    AddressingMode: str = ""
    SenderAlt: str = ""
    RecipientAlt: str = ""
    BroadcastListOwner: str = ""
    BroadcastRecipients: Optional[List[str]] = None
    ID: str = ""
    ServerID: int = 0
    Type: str = ""
    PushName: str = ""
    Timestamp: str = ""
    Category: str = ""
    Multicast: bool = False
    MediaType: str = ""
    Edit: str = ""
    MsgBotInfo: MsgBotInfo = field(default_factory=MsgBotInfo)
    MsgMetaInfo: MsgMetaInfo = field(default_factory=MsgMetaInfo)
    VerifiedName: Optional[VerifiedName] = None
    DeviceSentMeta: Optional[object] = None


@dataclass
class DeviceListMetadata:
    senderKeyHash: str = ""
    senderTimestamp: int = 0
    recipientKeyHash: str = ""
    recipientTimestamp: int = 0


@dataclass
class MessageContextInfo:
    deviceListMetadata: Optional[DeviceListMetadata] = None
    deviceListMetadataVersion: int = 0
    messageSecret: str = ""


@dataclass
class FeatureEligibilities:
    canBeReshared: bool = False


@dataclass
class ContextInfo:
    stanzaID: str = ""
    participant: str = ""
    quotedMessage: Optional[Dict[str, Any]] = None
    quotedType: int = 0
    pairedMediaType: int = 0
    statusSourceType: int = 0
    featureEligibilities: Optional[FeatureEligibilities] = None


@dataclass
class ImageMessage:
    URL: str = ""
    mimetype: str = ""
    caption: str = ""
    fileSHA256: str = ""
    fileLength: int = 0
    height: int = 0
    width: int = 0
    mediaKey: str = ""
    fileEncSHA256: str = ""
    directPath: str = ""
    mediaKeyTimestamp: int = 0
    JPEGThumbnail: str = ""
    contextInfo: Optional[ContextInfo] = None
    firstScanSidecar: str = ""
    firstScanLength: int = 0
    scansSidecar: str = ""
    scanLengths: Optional[List[int]] = None
    midQualityFileSHA256: str = ""
    imageSourceType: int = 0


@dataclass
class VideoMessage:
    URL: str = ""
    mimetype: str = ""
    caption: str = ""
    fileSHA256: str = ""
    fileLength: int = 0
    seconds: int = 0
    mediaKey: str = ""
    height: int = 0
    width: int = 0
    fileEncSHA256: str = ""
    directPath: str = ""
    mediaKeyTimestamp: int = 0
    JPEGThumbnail: str = ""
    contextInfo: Optional[ContextInfo] = None
    streamingSidecar: str = ""
    thumbnailDirectPath: str = ""
    thumbnailSHA256: str = ""
    thumbnailEncSHA256: str = ""
    gifPlayback: bool = False
    viewOnce: bool = False
    metadataURL: str = ""
    videoSourceType: int = 0
    externalShareFullVideoDurationInSeconds: int = 0


@dataclass
class ExtendedTextMessage:
    text: str = ""
    contextInfo: Optional[ContextInfo] = None


@dataclass
class ReactionKey:
    remoteJID: str = ""
    fromMe: bool = False
    ID: str = ""
    participant: str = ""


@dataclass
class ReactionMessage:
    key: Optional[ReactionKey] = None
    text: str = ""
    senderTimestampMS: int = 0


@dataclass
class SenderKeyDistributionMessage:
    groupID: str = ""
    axolotlSenderKeyDistributionMessage: str = ""


@dataclass
class InitialSecurityNotificationSettingSync:
    securityNotificationEnabled: bool = False


@dataclass
class AppStateSyncKeyID:
    keyID: str = ""


@dataclass
class AppStateSyncKeyFingerprint:
    rawID: int = 0
    currentIndex: int = 0
    deviceIndexes: Optional[List[int]] = None


@dataclass
class AppStateSyncKeyData:
    keyData: str = ""
    fingerprint: Optional[AppStateSyncKeyFingerprint] = None
    timestamp: int = 0


@dataclass
class AppStateSyncKey:
    keyID: Optional[AppStateSyncKeyID] = None
    keyData: Optional[AppStateSyncKeyData] = None


@dataclass
class AppStateSyncKeyShare:
    keys: Optional[List[AppStateSyncKey]] = None


@dataclass
class HistorySyncNotification:
    fileLength: int = 0
    syncType: int = 0
    chunkOrder: int = 0
    initialHistBootstrapInlinePayload: str = ""


@dataclass
class CompanionCanonicalUserNonceFetchRequestResponse:
    nonce: str = ""
    waFbid: str = ""
    forceRefresh: bool = False


@dataclass
class PeerDataOperationResult:
    companionCanonicalUserNonceFetchRequestResponse: Optional[CompanionCanonicalUserNonceFetchRequestResponse] = None


@dataclass
class PeerDataOperationRequestResponseMessage:
    peerDataOperationRequestType: int = 0
    peerDataOperationResult: Optional[List[PeerDataOperationResult]] = None


@dataclass
class AudioMessage:
    URL: str = ""
    mimetype: str = ""
    fileSHA256: str = ""
    fileLength: int = 0
    seconds: int = 0
    ptt: bool = False
    mediaKey: str = ""
    fileEncSHA256: str = ""
    directPath: str = ""
    mediaKeyTimestamp: int = 0
    contextInfo: Optional[ContextInfo] = None


@dataclass
class DocumentMessage:
    URL: str = ""
    mimetype: str = ""
    title: str = ""
    fileSHA256: str = ""
    fileLength: int = 0
    pageCount: int = 0
    mediaKey: str = ""
    fileName: str = ""
    fileEncSHA256: str = ""
    directPath: str = ""
    mediaKeyTimestamp: int = 0
    caption: str = ""
    contextInfo: Optional[ContextInfo] = None
    JPEGThumbnail: str = ""


@dataclass
class StickerMessage:
    URL: str = ""
    fileSHA256: str = ""
    fileEncSHA256: str = ""
    mediaKey: str = ""
    mimetype: str = ""
    directPath: str = ""
    fileLength: int = 0
    mediaKeyTimestamp: int = 0
    pngThumbnail: str = ""
    contextInfo: Optional[ContextInfo] = None
    height: int = 0
    width: int = 0
    isAnimated: bool = False
    isAvatar: bool = False
    isAISticker: bool = False
    isLottie: bool = False


@dataclass
class ProtocolMessage:
    type: int = 0
    initialSecurityNotificationSettingSync: Optional[InitialSecurityNotificationSettingSync] = None
    appStateSyncKeyShare: Optional[AppStateSyncKeyShare] = None
    historySyncNotification: Optional[HistorySyncNotification] = None
    peerDataOperationRequestResponseMessage: Optional[PeerDataOperationRequestResponseMessage] = None


@dataclass
class MessageContent:
    conversation: str = ""
    extendedTextMessage: Optional[ExtendedTextMessage] = None
    imageMessage: Optional[ImageMessage] = None
    videoMessage: Optional[VideoMessage] = None
    audioMessage: Optional[AudioMessage] = None
    documentMessage: Optional[DocumentMessage] = None
    stickerMessage: Optional[StickerMessage] = None
    reactionMessage: Optional[ReactionMessage] = None
    senderKeyDistributionMessage: Optional[SenderKeyDistributionMessage] = None
    protocolMessage: Optional[ProtocolMessage] = None
    messageContextInfo: Optional[MessageContextInfo] = None


@dataclass
class ContactAction:
    fullName: str = ""
    firstName: Optional[str] = None
    lidJID: str = ""
    saveOnPrimaryAddressbook: bool = False


@dataclass
class KeyExpirationAction:
    expiredKeyEpoch: int = 0


@dataclass
class MuteAction:
    muted: bool = False
    muteEndTimestamp: int = 0


@dataclass
class NuxAction:
    acknowledged: bool = False


@dataclass
class PrimaryVersionAction:
    version: str = ""


@dataclass
class StarAction:
    starred: bool = False


@dataclass
class AppStateEvent:
    Index: List[str] = field(default_factory=list)
    timestamp: int = 0
    contactAction: Optional[ContactAction] = None
    keyExpiration: Optional[KeyExpirationAction] = None
    muteAction: Optional[MuteAction] = None
    nuxAction: Optional[NuxAction] = None
    primaryVersionAction: Optional[PrimaryVersionAction] = None
    starAction: Optional[StarAction] = None


@dataclass
class PictureEvent:
    JID: str = ""
    Author: str = ""
    Timestamp: str = ""
    Remove: bool = False
    PictureID: str = ""


@dataclass
class ContactEvent:
    JID: str = ""
    Timestamp: str = ""
    Action: ContactAction = field(default_factory=ContactAction)
    FromFullSync: bool = False


@dataclass
class ReceiptEvent:
    Chat: str = ""
    Sender: str = ""
    IsFromMe: bool = False
    IsGroup: bool = False
    AddressingMode: str = ""
    SenderAlt: str = ""
    RecipientAlt: str = ""
    BroadcastListOwner: str = ""
    BroadcastRecipients: Optional[List[str]] = None
    MessageIDs: List[str] = field(default_factory=list)
    MessageSender: str = ""
    Timestamp: str = ""
    Type: str = ""


@dataclass
class BusinessNameEvent:
    JID: str = ""
    Message: MessageInfo = field(default_factory=MessageInfo)
    OldBusinessName: str = ""
    NewBusinessName: str = ""


@dataclass
class PushNameEvent:
    JID: str = ""
    JIDAlt: str = ""
    Message: MessageInfo = field(default_factory=MessageInfo)
    OldPushName: str = ""
    NewPushName: str = ""


@dataclass
class MessageEvent:
    Info: MessageInfo = field(default_factory=MessageInfo)
    Message: MessageContent = field(default_factory=MessageContent)
    IsEphemeral: bool = False
    IsViewOnce: bool = False
    IsViewOnceV2: bool = False
    IsViewOnceV2Extension: bool = False
    IsDocumentWithCaption: bool = False
    IsLottieSticker: bool = False
    IsBotInvoke: bool = False
    IsEdit: bool = False
    SourceWebMsg: Optional[object] = None
    UnavailableRequestID: str = ""
    RetryCount: int = 0
    NewsletterMeta: Optional[object] = None
    RawMessage: Optional[Dict[str, Any]] = None


@dataclass
class HistorySyncMessageKey:
    remoteJID: str = ""
    fromMe: bool = False
    ID: str = ""


@dataclass
class HistorySyncUserReceipt:
    userJID: str = ""
    receiptTimestamp: int = 0
    readTimestamp: int = 0
    playedTimestamp: int = 0


@dataclass
class HistorySyncReactionKey:
    remoteJID: str = ""
    fromMe: bool = False
    ID: str = ""
    participant: str = ""


@dataclass
class HistorySyncReaction:
    key: Optional[HistorySyncReactionKey] = None
    text: str = ""
    senderTimestampMS: int = 0
    unread: bool = False


@dataclass
class HistorySyncMediaData:
    localPath: str = ""


@dataclass
class HistorySyncReportingTokenInfo:
    reportingTag: str = ""


@dataclass
class HistorySyncPhotoChange:
    newPhoto: str = ""
    newPhotoID: int = 0
    oldPhoto: str = ""


@dataclass
class HistorySyncInnerMessage:
    key: HistorySyncMessageKey = field(default_factory=HistorySyncMessageKey)
    message: Optional[Dict[str, Any]] = None
    messageTimestamp: int = 0
    status: int = 0
    participant: str = ""
    isMentionedInStatus: bool = False
    messageSecret: str = ""
    originalSelfAuthorUserJIDString: str = ""
    userReceipt: Optional[List[HistorySyncUserReceipt]] = None
    reactions: Optional[List[HistorySyncReaction]] = None
    mediaData: Optional[HistorySyncMediaData] = None
    reportingTokenInfo: Optional[HistorySyncReportingTokenInfo] = None
    photoChange: Optional[HistorySyncPhotoChange] = None
    messageStubType: int = 0
    messageStubParameters: Optional[List[str]] = None
    revokeMessageTimestamp: int = 0
    broadcast: bool = False
    starred: bool = False
    duration: int = 0
    ephemeralOutOfSync: bool = False
    ephemeralStartTimestamp: int = 0
    bizPrivacyStatus: int = 0
    messageC2STimestamp: int = 0
    pollUpdates: Optional[List[Dict[str, Any]]] = None
    keepInChat: Optional[Dict[str, Any]] = None
    finalLiveLocation: Optional[Dict[str, Any]] = None
    groupHistoryBundleInfo: Optional[Dict[str, Any]] = None
    interactiveMessageAdditionalMetadata: Optional[Dict[str, Any]] = None


@dataclass
class HistorySyncMessageWrapper:
    message: HistorySyncInnerMessage = field(default_factory=HistorySyncInnerMessage)
    msgOrderID: int = 0


@dataclass
class DisappearingMode:
    initiator: int = 0


@dataclass
class MemberLabel:
    label: str = ""
    labelTimestamp: int = 0


@dataclass
class ConversationParticipant:
    userJID: str = ""
    rank: int = 0
    memberLabel: Optional[MemberLabel] = None


@dataclass
class HistorySyncConversation:
    ID: str = ""
    messages: Optional[List[HistorySyncMessageWrapper]] = None
    name: str = ""
    archived: bool = False
    conversationTimestamp: int = 0
    unreadCount: int = 0
    unreadMentionCount: int = 0
    readOnly: bool = False
    notSpam: bool = False
    markedAsUnread: bool = False
    ephemeralExpiration: int = 0
    ephemeralSettingTimestamp: int = 0
    endOfHistoryTransferType: int = 0
    contactPrimaryIdentityKey: str = ""
    accountLid: str = ""
    pnJID: str = ""
    lidJID: str = ""
    lidOriginType: str = ""
    tcToken: str = ""
    tcTokenTimestamp: int = 0
    tcTokenSenderTimestamp: int = 0
    disappearingMode: Optional[DisappearingMode] = None
    participant: Optional[List[ConversationParticipant]] = None
    pHash: str = ""
    suspended: bool = False
    commentsCount: int = 0
    locked: bool = False
    isDefaultSubgroup: bool = False
    isParentGroup: bool = False
    shareOwnPn: bool = False
    limitSharing: bool = False
    limitSharingInitiatedByMe: bool = False
    limitSharingSettingTimestamp: int = 0
    limitSharingTrigger: int = 0
    createdAt: int = 0
    createdBy: str = ""
    terminated: bool = False


@dataclass
class PhoneNumberToLidMapping:
    pnJID: str = ""
    lidJID: str = ""


@dataclass
class HistorySyncPushname:
    ID: str = ""
    pushname: str = ""


@dataclass
class PastParticipant:
    userJID: str = ""
    leaveReason: int = 0
    leaveTS: int = 0


@dataclass
class PastParticipantGroup:
    groupJID: str = ""
    pastParticipants: Optional[List[PastParticipant]] = None


@dataclass
class CallLogParticipant:
    userJID: str = ""
    callResult: int = 0


@dataclass
class CallLogRecord:
    callID: str = ""
    callCreatorJID: str = ""
    callType: int = 0
    callResult: int = 0
    duration: int = 0
    startTime: int = 0
    isIncoming: bool = False
    isVideo: bool = False
    isDndMode: bool = False
    silenceReason: int = 0
    groupJID: str = ""
    participants: Optional[List[CallLogParticipant]] = None


@dataclass
class RecentSticker:
    fileSHA256: str = ""
    fileLength: int = 0
    height: int = 0
    width: int = 0
    mimetype: str = ""
    isAvatarSticker: bool = False
    isLottie: bool = False
    lastStickerSentTS: int = 0
    weight: float = 0.0
    URL: str = ""
    directPath: str = ""
    fileEncSHA256: str = ""
    mediaKey: str = ""


@dataclass
class StatusV3Message:
    key: Optional[HistorySyncMessageKey] = None
    message: Optional[Dict[str, Any]] = None
    messageTimestamp: int = 0
    participant: str = ""
    isMentionedInStatus: bool = False
    messageSecret: str = ""
    mediaData: Optional[HistorySyncMediaData] = None
    reportingTokenInfo: Optional[HistorySyncReportingTokenInfo] = None


@dataclass
class HistorySyncData:
    syncType: int = 0
    conversations: Optional[List[HistorySyncConversation]] = None
    phoneNumberToLidMappings: Optional[List[PhoneNumberToLidMapping]] = None
    pushnames: Optional[List[HistorySyncPushname]] = None
    pastParticipants: Optional[List[PastParticipantGroup]] = None
    callLogRecords: Optional[List[CallLogRecord]] = None
    recentStickers: Optional[List[RecentSticker]] = None
    statusV3Messages: Optional[List[StatusV3Message]] = None
    globalSettings: Optional[Dict[str, Any]] = None
    chunkOrder: int = 0
    progress: int = 0
    companionMetaNonce: str = ""
    threadDsTimeframeOffset: int = 0
    threadIDUserSecret: str = ""


@dataclass
class HistorySyncEvent:
    Data: HistorySyncData = field(default_factory=HistorySyncData)
