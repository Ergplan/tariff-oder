import type { Me, UserOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { UsersAdmin } from "./users-admin";

export const dynamic = "force-dynamic";

/**
 * Users (administrators only): who may sign in and with what role.  Sign-in itself is
 * Google through IAP; an email listed here without IAP access still cannot reach the app,
 * and an IAP member not listed here is refused by the API.  Both lists must agree.
 */
export default async function UsersPage() {
  const [users, me] = await Promise.all([apiTry<UserOut[]>("/users"), apiTry<Me>("/me")]);
  return (
    <>
      <h1>Users</h1>
      <p className="muted">
        Three roles: <strong>analyst</strong> reads, <strong>reviewer</strong> decides, <strong>administrator</strong> uploads, assigns and
        manages users. Sign-in is Google through IAP: add the same address to the IAP group so the person can reach the app.
        Every change here is an audit event.
      </p>
      {users.error || !users.data ? <ErrorBanner error={users.error!} /> : <UsersAdmin initial={users.data} me={me.data?.email ?? ""} />}
    </>
  );
}
