import { NextResponse } from "next/server";
import { adminToken } from "@/lib/admin-auth";

export async function POST(request: Request) {
  const form = await request.formData();
  const key = form.get("key");
  const configured = process.env.ADMIN_UI_KEY;
  if (!configured || typeof key !== "string" || key !== configured) {
    return NextResponse.redirect(new URL("/admin?error=invalid", request.url), 303);
  }
  const response = NextResponse.redirect(new URL("/admin", request.url), 303);
  response.cookies.set("ds_admin_session", adminToken()!, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/admin",
    maxAge: 60 * 60 * 8,
  });
  return response;
}

export async function DELETE(request: Request) {
  const response = NextResponse.redirect(new URL("/admin", request.url), 303);
  response.cookies.delete("ds_admin_session");
  return response;
}
