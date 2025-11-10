// src/lib/share.ts - Enhanced share utility
export function buildShareUrls(url: string, msg: string) {
  const abs = new URL(url, window.location.origin).toString();
  const u = encodeURIComponent(abs);
  const t = encodeURIComponent(msg);
  
  return {
    reddit:   `https://www.reddit.com/submit?url=${u}&title=${t}`,
    twitter:  `https://twitter.com/intent/tweet?url=${u}&text=${t}`,
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${u}${msg ? `&quote=${t}` : ""}`,
    // LinkedIn only accepts ?url= and reads OG tags from the page
    linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
  };
}