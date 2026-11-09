export const isPhoto = f => f.type.startsWith('image/') || /\.(jpe?g|png|webp|gif|heic|heif)$/i.test(f.name);
export const isLivePackage = f => /\.livp$/i.test(f.name);
const stem = f => f.name.replace(/\.[^.]+$/, '').toLowerCase();
// Only pair unambiguous names. Renamed exports can still be paired manually.
export function matchingVideo(file, files) {
  if (!isPhoto(file)) return null;
  const photos = files.filter(f => isPhoto(f) && stem(f) === stem(file));
  const videos = files.filter(f => /\.(mov|mp4)$/i.test(f.name) && stem(f) === stem(file));
  return photos.length === 1 && videos.length === 1 ? videos[0] : null;
}
export function uploadItems(files, options) {
  const paired = new Set(options.map(o => o?.pair).filter(Boolean));
  return files.flatMap((file, i) => paired.has(file) ? [] : [{file, option: options[i] || {enabled:false, pair:null}}]);
}
