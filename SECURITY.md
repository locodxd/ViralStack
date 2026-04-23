# Security Policy

## Reportar una vulnerabilidad

Si encuentras una vulnerabilidad de seguridad en ViralStack, **no abras un issue público**. En su lugar:

1. Abre un GitHub Security Advisory privado: `Security` → `Report a vulnerability`.
2. O envía un email al maintainer del repositorio.

Intentaremos confirmar la recepción en menos de 72 horas y emitir un fix en cuanto sea viable.

## Buenas prácticas para usuarios

- **Nunca** commitees `.env`, `service_account.json`, `*_token.json`, `cookies.txt` o cualquier credencial.
- Activa `DASHBOARD_API_KEY` si expones el dashboard a Internet.
- Activa `DASHBOARD_ENABLE_CORS=false` (default) salvo que sepas qué orígenes permites.
- Pon el dashboard detrás de un reverse proxy con TLS (Caddy / Nginx / Cloudflare Tunnel).
- Rota periódicamente las claves API; el sistema soporta múltiples claves por proveedor.
- Revisa el log `storage/automation.log` antes de subirlo a un issue — el sistema enmascara secretos comunes (AIza..., sk-..., eyJ..., ghp_..., Bearer, xox[bapr]) pero **no es infalible**.

## Versiones soportadas

| Versión | Soporte         |
| ------- | --------------- |
| 1.1.x   | ✅ activa        |
| 1.0.x   | ⚠️ solo críticas |
| < 1.0   | ❌ no soportada  |
