import { LoadingLabel, Skeleton } from '../ui';

/** First load of the overview: each panel keeps its shape while its data arrives. */
export function PortfolioSkeleton() {
  return (
    <div aria-busy="true">
      <LoadingLabel>Loading your paper account</LoadingLabel>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="grid gap-2">
          <span className="kicker">Total equity</span>
          <Skeleton className="h-8 w-56" />
        </div>
        <div className="grid gap-2 md:justify-items-end">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-2.5 w-28" />
        </div>
      </div>
      <Skeleton className="h-3.5 w-full" />
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-2.5 w-24" />
        ))}
      </div>
      <div className="mt-6 grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <SleeveCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

export function SleeveCardSkeleton() {
  return (
    <div className="rounded-panel border border-line bg-panel" aria-hidden="true">
      <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
        <Skeleton className="h-3 w-36" />
        <Skeleton className="h-2.5 w-14" />
      </div>
      <div className="grid gap-3 px-4 py-4">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-2.5 w-20" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="grid grid-cols-[48px_minmax(0,1fr)_52px] items-center gap-2.5">
            <Skeleton className="h-2.5 w-10" />
            <Skeleton className="h-2 w-full" />
            <Skeleton className="ml-auto h-2.5 w-10" />
          </div>
        ))}
      </div>
    </div>
  );
}
