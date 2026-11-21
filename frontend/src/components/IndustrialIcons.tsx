import type { SVGProps } from "react";

function IconBase(props: SVGProps<SVGSVGElement> & { title?: string }) {
  const { title, children, className = "", ...rest } = props;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={title ? undefined : true}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export function IconCopy(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </IconBase>
  );
}

export function IconScanLine(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <path d="M3 7V5a2 2 0 0 1 2-2h2" />
      <path d="M17 3h2a2 2 0 0 1 2 2v2" />
      <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
      <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
      <path d="M7 12h10" />
    </IconBase>
  );
}

export function IconUsb(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <circle cx="10" cy="7" r="1" />
      <circle cx="4" cy="19" r="1" />
      <path d="M4.5 19 7 10.5" />
      <path d="M7 10.5 10 7" />
      <path d="M10 7l2.5 7" />
      <path d="M12.5 14 16 19" />
    </IconBase>
  );
}

export function IconArchive(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <rect width="20" height="5" x="2" y="3" rx="1" />
      <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" />
      <path d="M10 12h4" />
    </IconBase>
  );
}

export function IconMail(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <rect width="20" height="16" x="2" y="4" rx="2" />
      <path d="m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7" />
    </IconBase>
  );
}

export function IconInfo(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </IconBase>
  );
}

export function IconLock(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </IconBase>
  );
}

export function IconDroplets(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <path d="M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z" />
      <path d="M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97" />
    </IconBase>
  );
}

export function IconWifi(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <path d="M12 20h.01" />
      <path d="M2 8.82a15 15 0 0 1 20 0" />
      <path d="M5 12.859a10 10 0 0 1 14 0" />
      <path d="M8.5 16.429a5 5 0 0 1 7 0" />
    </IconBase>
  );
}

export function IconIdCard(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <rect width="20" height="14" x="2" y="5" rx="2" />
      <path d="M7 15h.01" />
      <path d="M11 12a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2" />
      <path d="M2 9h20" />
    </IconBase>
  );
}
