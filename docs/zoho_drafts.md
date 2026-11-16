# Zoho draft-only integration

AM Hub Liquidaciones > Preparar aviso de pago accepts PDFs, requires review, and exposes `Guardar borrador en Zoho (no enviar)` only with deployment secrets configured.

Configure a `[zoho_drafts]` block in Streamlit secrets (never Git) with `client_id`, `client_secret`, `refresh_token`, `account_id`, and `from_address`. Region currently restricted to Zoho US (`accounts.zoho.com`, `mail.zoho.com`). OAuth scopes used: `ZohoMail.messages.CREATE` and `ZohoMail.accounts.READ` for own-account discovery. Zoho CREATE also permits sending; the adapter intentionally has no send action and always sets `mode=draft`.

PDFs transfer only after the user checks review and clicks the explicit button. No task state is changed. Draft creation uses uploaded attachment references. A network timeout is ambiguous; the adapter never retries POST automatically and the UI blocks another attempt for the same reviewed data in that session. Reloading/opening another session can still duplicate a draft: inspect Zoho Borradores before retrying.

Verification: local unit suite; one synthetic PDF and test notice to own AM Consultora address was saved via API and observed in Zoho Borradores as an editable draft with attachment. No message was sent. Production hosting UI validation is recorded separately from this API check.

Fallback: .eml export is not a Zoho draft import guarantee. Copy text and attach original PDFs manually if integration unavailable. Calendar URL and ICS are explicit downloads/links, not automatic event creation.
