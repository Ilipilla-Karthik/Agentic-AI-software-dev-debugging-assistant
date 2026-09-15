function Panel({
  title,
  children,
  badge,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-line bg-panel ${className}`}>
      <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-faint">{title}</h3>
        {badge}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export default Panel;