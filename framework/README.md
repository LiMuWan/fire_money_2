# FireMoney Framework Layer

This package contains reusable engineering primitives that should stay independent
from FireMoney trading business logic.

Allowed here:

- JSON/config loading helpers
- Append-only local record stores
- Scheduler state persistence
- Notification transport abstractions
- HTTP/RPC boundary placeholders

Not allowed here:

- Stock strategy rules
- A-share calendar rules
- FireMoney DTOs or shared trading contracts
- Client UI rendering
- AkShare or Feishu product-specific adapters

