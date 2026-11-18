import React from 'react';
import {Comments} from './comments.jsx';
import {Reactions} from './emoji-picker.jsx';
import {LocationDisplay} from './locations.jsx';

export function EntryCard({entry, me, refresh, onEdit, onDelete, onGallery}) {
  const {media = [], tags = []} = entry;

  function openPhoto(photo) {
    const photos = media.filter(item => item.kind === 'image');
    onGallery({photos, index: photos.findIndex(item => item.id === photo.id)});
  }

  function closeActions(menu) {
    menu.open = false;
    menu.querySelector('summary').focus();
  }

  function manage(event, action) {
    closeActions(event.currentTarget.closest('details'));
    action(entry);
  }

  return <article className="entry" id={'entry-' + entry.id} tabIndex={-1}>
    <div className="entry-meta">
      <span className="avatar">{entry.author.slice(0, 1)}</span>
      <strong>{entry.author}</strong>
      <time>{new Date(entry.created * 1000).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'})}</time>
      {entry.user_id === me.id && <details className="entry-menu"
        onBlur={event => {
          if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
        }}
        onKeyDown={event => {
          if (event.key === 'Escape' && event.currentTarget.open) {
            event.preventDefault();
            event.stopPropagation();
            closeActions(event.currentTarget);
          }
        }}>
        <summary aria-label="这条记录的操作" title="这条记录的操作">···</summary>
        <div className="entry-menu-items">
          <button type="button" onClick={event => manage(event, onEdit)}>编辑</button>
          <button type="button" className="delete" onClick={event => manage(event, onDelete)}>删除这条记录</button>
        </div>
      </details>}
    </div>

    {media.length > 0 && <div className={`attachments count-${media.length}`}>
      {media.map(item => item.kind === 'image'
        ? <button type="button" className="photo-open" key={item.id}
            aria-label={item.live ? '放大查看实况照片' : '放大查看照片'} onClick={() => openPhoto(item)}>
            <img src={item.thumb || item.url} alt="当天的照片，点击放大" loading="lazy"/>
            {item.live && <span className="live-badge">◎ LIVE</span>}
          </button>
        : <video key={item.id} controls preload="none" playsInline poster={item.thumb || undefined} src={item.url}/>)}
    </div>}
    {entry.body && <p className="entry-body">{entry.body}</p>}
    {(entry.location || tags.length > 0) && <div className="entry-caption">
      <LocationDisplay value={entry.location}/>
      {tags.length > 0 && <div className="entry-tags" aria-label="帖子标签">
        {tags.map(tag => <span className="tag-chip" key={tag.id}># {tag.name}</span>)}
      </div>}
    </div>}

    <Reactions kind="entries" target={entry} me={me} refresh={refresh}/>
    <Comments entry={entry} me={me} refresh={refresh}/>
  </article>;
}
