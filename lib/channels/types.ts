/**
 * PCL AI Social Assistant - Unified Channel Types
 *
 * These types define the normalized message format that all channels
 * (Telegram, Instagram DM) use before routing to the AI brain.
 *
 * Routing-critical identifiers are explicit, not hidden in metadata.
 */

/**
 * Supported channel types.
 * Extensible for future channels.
 */
export type ChannelType = 'telegram' | 'instagram_dm';

/**
 * Message type classification.
 */
export type IncomingMessageType = 'text' | 'command' | 'callback' | 'unsupported';

/**
 * Outgoing message role (who sends it).
 */
export type MessageRole = 'user' | 'ai' | 'human' | 'system';

/**
 * Conversation state in AI brain.
 */
export type ConversationState = 'AI_ACTIVE' | 'HUMAN_REQUIRED' | 'HUMAN_ACTIVE';

/**
 * Unified incoming message format.
 *
 * All channel adapters (Telegram, Instagram) normalize their events
 * to this format before enqueueing for AI processing.
 *
 * Idempotency is guaranteed by the tuple:
 *   (workspaceId, channel, channelAccountId, channelMessageId)
 *
 * Which uniquely identifies a message at the platform level.
 */
export interface IncomingMessage {
  /**
   * Workspace ID (required for multi-tenancy).
   */
  workspaceId: string;

  /**
   * Channel type.
   */
  channel: ChannelType;

  /**
   * Platform-specific account identifier.
   * Telegram: bot account identifier (e.g., bot_id from getMe)
   * Instagram: Instagram account ID (e.g., business account ID)
   *
   * Used for routing to the correct account/bot and for idempotency.
   */
  channelAccountId: string;

  /**
   * Platform-specific user identifier.
   * Telegram: chat_id or user_id
   * Instagram: IGSID (sender.id from webhook)
   *
   * Used to find or create ChannelIdentity and Contact.
   */
  channelUserId: string;

  /**
   * Platform-specific message identifier.
   * Telegram: update_id (for webhook event idempotency)
   * Instagram: message mid or comment id (for message idempotency)
   *
   * Must be non-null for idempotency enforcement.
   *
   * IMPORTANT: Telegram update_id is webhook-event scoped, not message scoped.
   * For message-level idempotency (to avoid processing the same message twice),
   * use message.message_id. For webhook delivery idempotency (to avoid processing
   * the same webhook delivery twice), use update_id.
   *
   * In Phase B, the webhook handler will use update_id for delivery idempotency,
   * and message.message_id will be stored in channelMessageId for message deduplication.
   */
  channelMessageId: string;

  /**
   * Message type classification.
   */
  type: IncomingMessageType;

  /**
   * Message text content.
   * Empty string if no text content.
   */
  text: string;

  /**
   * Message timestamp (UTC).
   */
  timestamp: Date;

  /**
   * Channel-specific metadata.
   *
   * Examples:
   * - Telegram: { chat_type, message_id, user, ... }
   * - Instagram: { sender, media_type, ... }
   *
   * Do NOT store routing-critical fields here; they are explicit in this interface.
   */
  metadata: Record<string, unknown>;
}

/**
 * Unified outgoing message format.
 *
 * Used by the AI brain and adapters to send replies back to the platform.
 */
export interface OutgoingMessage {
  /**
   * Workspace ID (required for multi-tenancy).
   */
  workspaceId: string;

  /**
   * Channel type (determines which adapter sends this).
   */
  channel: ChannelType;

  /**
   * Platform-specific account identifier (which account/bot sends this).
   */
  channelAccountId: string;

  /**
   * Platform-specific user identifier (recipient).
   */
  channelUserId: string;

  /**
   * Message text content.
   */
  text: string;

  /**
   * Channel-specific formatting options.
   *
   * Examples:
   * - Telegram: { parse_mode: 'HTML', reply_markup: {...} }
   * - Instagram: { buttons: [...] }
   */
  formatting?: {
    telegram?: Record<string, unknown>;
    instagram?: Record<string, unknown>;
  };

  /**
   * Optional reply-to message ID.
   * Telegram: reply_to_message_id
   * Instagram: thread context
   */
  replyToMessageId?: string;

  /**
   * Conversation ID (for tracking and association).
   */
  conversationId: string;
}

/**
 * Channel adapter interface (for future implementations).
 *
 * Each channel (Telegram, Instagram) implements these methods.
 */
export interface ChannelAdapter {
  /**
   * Parse platform webhook payload to normalized IncomingMessage.
   */
  parseIncomingMessage(
    payload: Record<string, unknown>
  ): IncomingMessage | null;

  /**
   * Send outgoing message via platform API.
   */
  sendMessage(message: OutgoingMessage): Promise<{ success: boolean; messageId?: string; error?: string }>;

  /**
   * Verify webhook signature.
   */
  verifyWebhookSignature(
    payload: string,
    signature: string
  ): boolean;
}

/**
 * Conversation context for AI processing.
 *
 * Contains the current conversation state, recent message history,
 * and system information needed for LLM context building.
 */
export interface ConversationContext {
  workspaceId: string;
  conversationId: string;
  contactId: string;
  channelIdentityId: string;
  channel: ChannelType;
  state: ConversationState;
  lastMessageAt: Date;
  createdAt: Date;
}

/**
 * Message history entry for context building.
 *
 * Used when loading conversation history for LLM context.
 */
export interface MessageHistory {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: Date;
  aiMetadata?: {
    provider?: string;
    model?: string;
    latency_ms?: number;
    tokens_used?: number;
  };
}
