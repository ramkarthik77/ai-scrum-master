/**
 * Cloudflare Worker that fronts the AI Scrum Master web app running in a
 * Cloudflare Container (the repo's Dockerfile).
 *
 * All traffic goes to ONE named container instance ("main"), because the app
 * keeps login sessions in memory. When the container sleeps after inactivity,
 * users simply sign in again.
 */
import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  SCRUM_AGENT: DurableObjectNamespace<ScrumAgentContainer>;
  // Secrets (wrangler secret put ...) — all optional
  ANTHROPIC_API_KEY?: string;
  OPENAI_API_KEY?: string;
  GITHUB_OAUTH_CLIENT_ID?: string;
  GITHUB_OAUTH_CLIENT_SECRET?: string;
  // Plain vars (wrangler.jsonc "vars")
  SCRUM_AGENT_MODEL?: string;
  ALLOW_TOKEN_LOGIN?: string;
  SESSION_TTL_HOURS?: string;
  PUBLIC_URL?: string;
}

const PASS_THROUGH: (keyof Env)[] = [
  "ANTHROPIC_API_KEY",
  "OPENAI_API_KEY",
  "GITHUB_OAUTH_CLIENT_ID",
  "GITHUB_OAUTH_CLIENT_SECRET",
  "SCRUM_AGENT_MODEL",
  "ALLOW_TOKEN_LOGIN",
  "SESSION_TTL_HOURS",
  "PUBLIC_URL",
];

export class ScrumAgentContainer extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = "30m";
  pingEndpoint = "container/healthz";

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env);
    const vars: Record<string, string> = {};
    for (const k of PASS_THROUGH) {
      const v = env[k];
      if (typeof v === "string" && v !== "") vars[k] = v;
    }
    this.envVars = vars;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const headers = new Headers(request.headers);
    // Let the app build correct absolute URLs (OAuth callback) and secure cookies.
    headers.set("X-Forwarded-Proto", url.protocol.replace(":", ""));
    headers.set("X-Forwarded-Host", url.host);
    const forwarded = new Request(request, { headers });
    return getContainer(env.SCRUM_AGENT, "main").fetch(forwarded);
  },
} satisfies ExportedHandler<Env>;
