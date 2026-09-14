import { getNeonAuth } from "@/lib/auth/server";

type AuthRouteContext = { params: Promise<{ path: string[] }> };

function unavailable() {
  return Response.json(
    { code: "AUTH_PROVIDER_UNAVAILABLE", detail: "Account sign-in is not configured." },
    { status: 503 },
  );
}

export async function GET(request: Request, context: AuthRouteContext) {
  const auth = getNeonAuth();
  return auth ? auth.handler().GET(request, context) : unavailable();
}

export async function POST(request: Request, context: AuthRouteContext) {
  const auth = getNeonAuth();
  return auth ? auth.handler().POST(request, context) : unavailable();
}

export async function PUT(request: Request, context: AuthRouteContext) {
  const auth = getNeonAuth();
  return auth ? auth.handler().PUT(request, context) : unavailable();
}

export async function DELETE(request: Request, context: AuthRouteContext) {
  const auth = getNeonAuth();
  return auth ? auth.handler().DELETE(request, context) : unavailable();
}

export async function PATCH(request: Request, context: AuthRouteContext) {
  const auth = getNeonAuth();
  return auth ? auth.handler().PATCH(request, context) : unavailable();
}
