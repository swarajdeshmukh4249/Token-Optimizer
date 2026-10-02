const { memo, useCallback, useEffect, useRef } = React;

const GlowingEffect = memo(function GlowingEffect({
  blur = 0,
  inactiveZone = 0.7,
  proximity = 0,
  spread = 20,
  variant = "default",
  glow = false,
  className = "",
  movementDuration = 2,
  borderWidth = 1,
  disabled = true,
}) {
  const containerRef = useRef(null);
  const lastPosition = useRef({ x: 0, y: 0 });
  const animationFrameRef = useRef(0);

  const handleMove = useCallback((e) => {
    if (!containerRef.current) return;

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    animationFrameRef.current = requestAnimationFrame(() => {
      const element = containerRef.current;
      if (!element) return;

      const { left, top, width, height } = element.getBoundingClientRect();
      const mouseX = e?.x ?? lastPosition.current.x;
      const mouseY = e?.y ?? lastPosition.current.y;

      if (e) {
        lastPosition.current = { x: mouseX, y: mouseY };
      }

      const center = [left + width * 0.5, top + height * 0.5];
      const distanceFromCenter = Math.hypot(mouseX - center[0], mouseY - center[1]);
      const inactiveRadius = 0.5 * Math.min(width, height) * inactiveZone;

      if (distanceFromCenter < inactiveRadius) {
        element.style.setProperty("--active", "0");
        return;
      }

      const isActive = mouseX > left - proximity &&
        mouseX < left + width + proximity &&
        mouseY > top - proximity &&
        mouseY < top + height + proximity;

      element.style.setProperty("--active", isActive ? "1" : "0");

      if (!isActive) return;

      const currentAngle = parseFloat(element.style.getPropertyValue("--start")) || 0;
      let targetAngle = (180 * Math.atan2(mouseY - center[1], mouseX - center[0])) / Math.PI + 90;

      const angleDiff = ((targetAngle - currentAngle + 180) % 360) - 180;
      const newAngle = currentAngle + angleDiff;

      if (window.Motion && window.Motion.animate) {
        window.Motion.animate(currentAngle, newAngle, {
          duration: movementDuration,
          ease: [0.16, 1, 0.3, 1],
          onUpdate: (value) => {
            element.style.setProperty("--start", String(value));
          },
        });
      }
    });
  }, [inactiveZone, proximity, movementDuration]);

  useEffect(() => {
    if (disabled) return;

    const handleScroll = () => handleMove();
    const handlePointerMove = (e) => handleMove(e);

    window.addEventListener("scroll", handleScroll, { passive: true });
    document.body.addEventListener("pointermove", handlePointerMove, { passive: true });

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      window.removeEventListener("scroll", handleScroll);
      document.body.removeEventListener("pointermove", handlePointerMove);
    };
  }, [handleMove, disabled]);

  const gradientStyle = variant === "white" 
    ? "repeating-conic-gradient(from 236.84deg at 50% 50%, var(--black), var(--black) calc(25% / var(--repeating-conic-gradient-times)))"
    : "radial-gradient(circle, #d4ff3f 10%, #d4ff3f00 20%), radial-gradient(circle at 40% 40%, #67e8f9 5%, #67e8f900 15%), radial-gradient(circle at 60% 60%, #ff6b35 10%, #ff6b3500 20%), radial-gradient(circle at 40% 60%, #a3e635 10%, #a3e63500 20%), repeating-conic-gradient(from 236.84deg at 50% 50%, #d4ff3f 0%, #67e8f9 calc(25% / var(--repeating-conic-gradient-times)), #ff6b35 calc(50% / var(--repeating-conic-gradient-times)), #a3e635 calc(75% / var(--repeating-conic-gradient-times)), #d4ff3f calc(100% / var(--repeating-conic-gradient-times)))";

  return React.createElement(React.Fragment, null,
    React.createElement("div", {
      className: cn(
        "pointer-events-none absolute -inset-px hidden rounded-[inherit] border opacity-0 transition-opacity",
        glow && "opacity-100",
        variant === "white" && "border-white",
        disabled && "!block"
      )
    }),
    React.createElement("div", {
      ref: containerRef,
      style: {
        "--blur": `${blur}px`,
        "--spread": spread,
        "--start": "0",
        "--active": "0",
        "--glowingeffect-border-width": `${borderWidth}px`,
        "--repeating-conic-gradient-times": "5",
        "--gradient": gradientStyle
      },
      className: cn(
        "pointer-events-none absolute inset-0 rounded-[inherit] opacity-100 transition-opacity",
        glow && "opacity-100",
        blur > 0 && "blur-[var(--blur)]",
        className,
        disabled && "!hidden"
      )
    },
      React.createElement("div", {
        className: cn(
          "glow rounded-[inherit]",
          'after:content-[""] after:rounded-[inherit] after:absolute after:inset-[calc(-1*var(--glowingeffect-border-width))]',
          "after:[border:var(--glowingeffect-border-width)_solid_transparent]",
          "after:[background:var(--gradient)] after:[background-attachment:fixed]",
          "after:opacity-[var(--active)] after:transition-opacity after:duration-300",
          "after:[mask-clip:padding-box,border-box]",
          "after:[mask-composite:intersect]",
          "after:[mask-image:linear-gradient(#0000,#0000),conic-gradient(from_calc((var(--start)-var(--spread))*1deg),#00000000_0deg,#fff,#00000000_calc(var(--spread)*2deg))]"
        )
      })
    )
  );
});