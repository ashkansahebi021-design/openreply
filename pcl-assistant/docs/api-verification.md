# API verification — 2026-10-03

Official Meta pages were fetched successfully through Python HTTPS (web reader was rate-limited). Checked against existing adapters; no unofficial Instagram automation used.

## private-replies

Source: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/private-replies

Step 4. Your app can send this private reply within 7 days of the creation time of the comment, excepting Instagram Live, where replies can only be sent during the live broadcast. The private reply message includes a link to the commented post.
| **Access Tokens** | * Instagram User access token | * [Facebook Page access token](https://developers.facebook.com/documentation/facebook-login/guides/access-tokens) |
| [**Permissions**](https://developers.facebook.com/docs/permissions/reference#i) | * `instagram_business_basic`<br>* `instagram_business_manage_comments` | * `instagram_basic`<br>* `instagram_manage_comments`<br>* `pages_read_engagement`<br><br>If the app user was granted a role on the [Page](https://developers.facebook.com/documentation/instagram-platform/overview#pages) connected to your app user's Instagram professional account via the Business Manager, your app will also need:<br><br>* `ads_management`<br>* `ads_read` |
* Only one message can be sent to the commenter
* The message must be sent within 7 days of the comment was made on the post or reel
* Follow-up messages can only be sent if the recipient responds, and must be sent within 24 hours of the response

## messaging

Source: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api

Only after an Instagram user has sent your app user's Instagram professional account a message can your app send a message to the Instagram user. Your app has 24 hours to respond to any message sent from an Instagram user to your app user.
* Advanced Access if your app serves Instagram professional accounts you don't own or manage
* Standard Access if your app serves Instagram professional accounts you own or manage or have added to your app in the App Dashboard; Some features may not work properly until your app has been granted Advanced Access
* `instagram_business_basic`
* `instagram_business_manage_messages`
Message text must be UTF-8 and be a 1000 bytes or less. Links must be valid formatted URLs.
curl -X POST "https://graph.instagram.com/v25.0/<IG_ID>/messages"
curl -X POST "https://graph.instagram.com/v25.0/<IG_ID>/messages"
curl -X POST "https://graph.instagram.com/v25.0/<IG_ID>/messages"
curl -X POST "https://graph.instagram.com/v25.0/<IG_ID>/messages"
curl -X POST "https://graph.instagram.com/v25.0/<IG_ID>/messages"
curl -X POST "https://graph.instagram.com/v25.0/<IG_ID>/messages"

## login

Source: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login

**Note:** This API setup does not require a Facebook Page to be linked to the Instagram professional account.
* `instagram_business_basic`
* `instagram_business_content_publish`
* `instagram_business_manage_messages`
* `instagram_business_manage_comments`

## webhooks

Source: https://developers.facebook.com/docs/instagram-platform/webhooks

| **Access level** | Advanced Access | Advanced Access for `comments` and `live_comments` | Advanced Access |
| **Endpoints** | [`/<INSTAGRAM_ACCOUNT_ID>`](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user) or `/me` – Represents your app user's Instagram profession account | [`/<PAGE_ID>`](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user) or `/me` – Represents the Facebook Page linked to your app user's Instagram professional account | [`/<PAGE_ID>`](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user) or `/me` – Represents the Facebook Page linked to your app user's Instagram professional account |
| **IDs** | The ID of your app user's Instagram professional account | The ID of the Facebook Page linked to your app user's Instagram professional account | The ID of the Facebook Page linked to your app user's Instagram professional account |
| **Basic Permission** | `instagram_business_basic` | `instagram_basic` | `instagram_basic` |
- Advanced Access is required to receive `comments` and `live_comments` webhook notifications.
- Notifications for `story_insights` events will only show metrics for the first 24 hours, before the story expires, even if the story is a highlight.
X-Hub-Signature-256: sha256={super-long-SHA256-signature}
We sign all Event Notification payloads with a **SHA256** signature and include the signature in the request's `X-Hub-Signature-256` header, preceded with `sha256=`. You don't have to validate the payload, but you should.
1. Generate a **SHA256** signature using the payload and your app's **App Secret**.
1. Compare your signature to the signature in the `X-Hub-Signature-256` header (everything after `sha256=`). If the signatures match, the payload is genuine.
| `/me` | Represents your app user's Instagram professional account ID or the Facebook Page ID that is linked to your app user's Instagram professional account |
| `<ACCESS_TOKEN>` | App user's Instagram User access token or Facebook Page access token. |

Comment webhook entry.time is notification time, not creation time. Fetch missing comment timestamp from the Graph comment endpoint; fail closed if unavailable. Live comment replies excluded. No HUMAN_AGENT tag used for automated replies.

OpenAI Responses API structured output, store:false, configurable model gpt-4.1-mini verified at https://developers.openai.com/api/docs/guides/structured-outputs and https://developers.openai.com/api/docs/models/gpt-4.1-mini.

n8n current official Docker docs report stable 2.41.6; pin image after registry confirmation. Official paths moved to /deploy/host-n8n/.

Railway https://railway.com/pricing reviewed: Hobby $5/month minimum, usage beyond credits extra. Free resource/storage restrictions unsuitable for promising durable always-on runtime + n8n without checking actual usage and available volumes. No paid host selected, resource created, or deployment triggered.
