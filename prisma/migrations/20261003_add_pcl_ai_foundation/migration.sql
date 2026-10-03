-- ============================================================================
-- PCL AI SOCIAL ASSISTANT FOUNDATION MODELS
-- ============================================================================

-- Contact: represents a human user interacting with PCL
CREATE TABLE "Contact" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "displayName" TEXT,
    "email" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Contact_pkey" PRIMARY KEY ("id")
);

-- ChannelIdentity: maps a Contact to a specific channel (Telegram, Instagram DM)
CREATE TABLE "ChannelIdentity" (
    "id" TEXT NOT NULL,
    "contactId" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "channel" TEXT NOT NULL,
    "channelUserId" TEXT NOT NULL,
    "channelAccountId" TEXT NOT NULL,
    "channelUsername" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ChannelIdentity_pkey" PRIMARY KEY ("id")
);

-- Conversation: represents a thread per channel
CREATE TABLE "Conversation" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "contactId" TEXT NOT NULL,
    "channelIdentityId" TEXT NOT NULL,
    "channel" TEXT NOT NULL,
    "state" TEXT NOT NULL DEFAULT 'AI_ACTIVE',
    "handledByUserId" TEXT,
    "lastMessageAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Conversation_pkey" PRIMARY KEY ("id")
);

-- Message: individual messages with idempotency key
CREATE TABLE "Message" (
    "id" TEXT NOT NULL,
    "conversationId" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "channel" TEXT NOT NULL,
    "channelAccountId" TEXT NOT NULL,
    "channelMessageId" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "aiMetadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Message_pkey" PRIMARY KEY ("id")
);

-- ConversationHandoff: track human handoff state
CREATE TABLE "ConversationHandoff" (
    "id" TEXT NOT NULL,
    "conversationId" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "initiatedBy" TEXT NOT NULL,
    "initiatedReason" TEXT,
    "handoffAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "acknowledgedAt" TIMESTAMP(3),
    "acknowledgedBy" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ConversationHandoff_pkey" PRIMARY KEY ("id")
);

-- LLMProviderConfig: non-secret LLM configuration (no API keys stored)
CREATE TABLE "LLMProviderConfig" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "isEnabled" BOOLEAN NOT NULL DEFAULT true,
    "settings" JSONB NOT NULL DEFAULT '{}',
    "fallbackProvider" TEXT,
    "fallbackModel" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "LLMProviderConfig_pkey" PRIMARY KEY ("id")
);

-- KnowledgeBase: PCL knowledge items
CREATE TABLE "KnowledgeBase" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "tags" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "relevanceScore" DOUBLE PRECISION NOT NULL DEFAULT 1,
    "lastVerifiedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "KnowledgeBase_pkey" PRIMARY KEY ("id")
);

-- AIProcessingLog: track AI processing for observability
CREATE TABLE "AIProcessingLog" (
    "id" TEXT NOT NULL,
    "conversationId" TEXT NOT NULL,
    "messageId" TEXT,
    "workspaceId" TEXT NOT NULL,
    "stage" TEXT NOT NULL,
    "provider" TEXT,
    "model" TEXT,
    "latencyMs" INTEGER,
    "inputTokens" INTEGER,
    "outputTokens" INTEGER,
    "success" BOOLEAN NOT NULL,
    "errorMessage" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AIProcessingLog_pkey" PRIMARY KEY ("id")
);

-- Create indexes for performance
CREATE INDEX "Contact_workspaceId_idx" ON "Contact"("workspaceId");
CREATE INDEX "Contact_email_idx" ON "Contact"("email");

CREATE UNIQUE INDEX "ChannelIdentity_workspaceId_channel_channelAccountId_channelUserId_key" ON "ChannelIdentity"("workspaceId", "channel", "channelAccountId", "channelUserId");
CREATE INDEX "ChannelIdentity_contactId_idx" ON "ChannelIdentity"("contactId");
CREATE INDEX "ChannelIdentity_workspaceId_idx" ON "ChannelIdentity"("workspaceId");
CREATE INDEX "ChannelIdentity_channel_idx" ON "ChannelIdentity"("channel");

CREATE INDEX "Conversation_workspaceId_idx" ON "Conversation"("workspaceId");
CREATE INDEX "Conversation_contactId_idx" ON "Conversation"("contactId");
CREATE INDEX "Conversation_state_idx" ON "Conversation"("state");
CREATE INDEX "Conversation_lastMessageAt_idx" ON "Conversation"("lastMessageAt");
CREATE INDEX "Conversation_channel_idx" ON "Conversation"("channel");

CREATE INDEX "Message_conversationId_idx" ON "Message"("conversationId");
CREATE INDEX "Message_workspaceId_idx" ON "Message"("workspaceId");
CREATE INDEX "Message_role_idx" ON "Message"("role");
CREATE UNIQUE INDEX "Message_workspaceId_channel_channelAccountId_channelMessageId_key" ON "Message"("workspaceId", "channel", "channelAccountId", "channelMessageId");

CREATE INDEX "ConversationHandoff_workspaceId_idx" ON "ConversationHandoff"("workspaceId");
CREATE INDEX "ConversationHandoff_handoffAt_idx" ON "ConversationHandoff"("handoffAt");
CREATE UNIQUE INDEX "ConversationHandoff_conversationId_key" ON "ConversationHandoff"("conversationId");

CREATE INDEX "LLMProviderConfig_workspaceId_idx" ON "LLMProviderConfig"("workspaceId");
CREATE UNIQUE INDEX "LLMProviderConfig_workspaceId_key" ON "LLMProviderConfig"("workspaceId");

CREATE INDEX "KnowledgeBase_workspaceId_idx" ON "KnowledgeBase"("workspaceId");
CREATE INDEX "KnowledgeBase_category_idx" ON "KnowledgeBase"("category");
CREATE INDEX "KnowledgeBase_isActive_idx" ON "KnowledgeBase"("isActive");

CREATE INDEX "AIProcessingLog_workspaceId_idx" ON "AIProcessingLog"("workspaceId");
CREATE INDEX "AIProcessingLog_conversationId_idx" ON "AIProcessingLog"("conversationId");
CREATE INDEX "AIProcessingLog_stage_idx" ON "AIProcessingLog"("stage");
CREATE INDEX "AIProcessingLog_createdAt_idx" ON "AIProcessingLog"("createdAt");

-- Add foreign keys
ALTER TABLE "Contact" ADD CONSTRAINT "Contact_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;

ALTER TABLE "ChannelIdentity" ADD CONSTRAINT "ChannelIdentity_contactId_fkey" FOREIGN KEY ("contactId") REFERENCES "Contact"("id") ON DELETE CASCADE;
ALTER TABLE "ChannelIdentity" ADD CONSTRAINT "ChannelIdentity_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;

ALTER TABLE "Conversation" ADD CONSTRAINT "Conversation_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;
ALTER TABLE "Conversation" ADD CONSTRAINT "Conversation_contactId_fkey" FOREIGN KEY ("contactId") REFERENCES "Contact"("id") ON DELETE CASCADE;
ALTER TABLE "Conversation" ADD CONSTRAINT "Conversation_channelIdentityId_fkey" FOREIGN KEY ("channelIdentityId") REFERENCES "ChannelIdentity"("id") ON DELETE CASCADE;

ALTER TABLE "Message" ADD CONSTRAINT "Message_conversationId_fkey" FOREIGN KEY ("conversationId") REFERENCES "Conversation"("id") ON DELETE CASCADE;
ALTER TABLE "Message" ADD CONSTRAINT "Message_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;

ALTER TABLE "ConversationHandoff" ADD CONSTRAINT "ConversationHandoff_conversationId_fkey" FOREIGN KEY ("conversationId") REFERENCES "Conversation"("id") ON DELETE CASCADE;
ALTER TABLE "ConversationHandoff" ADD CONSTRAINT "ConversationHandoff_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;

ALTER TABLE "LLMProviderConfig" ADD CONSTRAINT "LLMProviderConfig_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;

ALTER TABLE "KnowledgeBase" ADD CONSTRAINT "KnowledgeBase_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;

ALTER TABLE "AIProcessingLog" ADD CONSTRAINT "AIProcessingLog_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE;
