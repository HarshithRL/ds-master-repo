export default function AccessDeniedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-2 text-center px-4">
      <h1 className="text-xl font-semibold">Access denied</h1>
      <p className="text-muted-foreground max-w-md">
        Your account isn&apos;t enabled for this app, or your email domain isn&apos;t allowed.
        Contact your administrator to get access.
      </p>
    </div>
  );
}
