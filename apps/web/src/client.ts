export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/v1" + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.details
        ?.map(
          (x: { field: string; message: string }) => `${x.field}: ${x.message}`,
        )
        .join("; ") ||
        error.message ||
        "Request failed.",
    );
  }
  return response.json();
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export async function waitJob(id: string) {
  for (let i = 0; i < 180; i++) {
    const job = await api<{
      status: string;
      error?: string;
      warnings?: string[];
    }>("/jobs/" + id);
    if (job.status === "FAILED")
      throw new Error(job.error || "Operation failed.");
    if (["SUCCEEDED", "PARTIAL"].includes(job.status)) return job;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(
    "The operation is still running. Reopen the workspace later to check its status.",
  );
}
