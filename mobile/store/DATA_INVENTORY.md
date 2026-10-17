# Store disclosure worksheet

This is a code inventory, not a submitted privacy declaration. Confirm backend/service behavior and retention with the operator before completing App Store privacy or Play Data Safety forms.

| Data | Use visible in code | Review needed |
| --- | --- | --- |
| Account email, username, name, country, phone | Registration, authentication, profiles, password recovery | Required/optional fields, retention, deletion |
| Profiles, posts, portfolios, course content, event/competition entries | Community publication and collaboration | Audience/visibility, media storage and moderation |
| Messages and uploaded files/voice | Conversations, read state | Server access, media retention, backups |
| Camera/microphone streams and screen sharing | Calls and classrooms | WebRTC peer/TURN transport; verify any recording policy |
| Expo push token and device platform | Incoming-call notifications | Expo/APNs/FCM sharing, logout/deletion cleanup |
| VoIP device token, call identifiers and participant state | PushKit/CallKit and native incoming calls | APNs transport, token retention, expired-call cleanup |
| Interests, recommendations, impressions and dismissals | Discovery and ranking | Verify enabled production flags, profiling disclosures and retention |
| Blocks and content reports | Safety and moderation | Report handling, retained evidence, operator response process |
| Credentials | SecureStore and backend authentication | Token revocation and access controls |

No native billing flow is enabled. Do not claim purchases, payment verification, or end-to-end message encryption. WebRTC transport encryption is separate from message-storage policies. Reports are retained after account deletion with the reporter relation removed; upload-storage and backup retention require the operator's policy.

Before store submission, provide public privacy, terms, support, and external account-deletion instructions URLs, real store screenshots from signed native builds, review accounts, content/age ratings, and accurate data-use declarations. No store login, submission, or publication is performed by these files.
