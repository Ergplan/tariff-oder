import { redirect } from "next/navigation";

/** The case list lives on the client home. */
export default function CasesIndex() {
  redirect("/client");
}
