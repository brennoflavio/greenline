package main

import "testing"

func TestBuildMessageContextPreservesExplicitGroupLIDParticipant(t *testing.T) {
	ctx, err := (&Service{}).buildMessageContext(&SendMessageArgs{
		ChatJID:             "333@g.us",
		ReplyToMessageID:    "quoted-message",
		ReplyParticipantJID: "222@lid",
	})
	if err != nil {
		t.Fatalf("buildMessageContext returned error: %v", err)
	}
	if ctx == nil {
		t.Fatal("buildMessageContext returned nil context")
	}
	if got := ctx.GetParticipant(); got != "222@lid" {
		t.Fatalf("participant = %q, want %q", got, "222@lid")
	}
}
