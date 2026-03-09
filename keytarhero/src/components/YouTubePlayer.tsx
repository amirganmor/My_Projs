interface YouTubePlayerProps {
  containerId: string;
  backgroundMode?: boolean;
}

export default function YouTubePlayer({ containerId, backgroundMode }: YouTubePlayerProps) {
  return (
    <div
      className={
        backgroundMode
          ? 'fixed inset-0 z-0 overflow-hidden pointer-events-none'
          : 'fixed -left-[9999px] -top-[9999px] w-px h-px overflow-hidden'
      }
    >
      {backgroundMode && (
        <div className="absolute inset-0 backdrop-blur-lg bg-black/70 z-10" />
      )}
      <div
        id={containerId}
        className={
          backgroundMode
            ? 'absolute inset-0 w-full h-full [&>iframe]:w-full [&>iframe]:h-full'
            : ''
        }
      />
    </div>
  );
}
