import copy, json, math, re, subprocess, uuid, pathlib, datetime, threading, queue

ROOT=pathlib.Path(__file__).resolve().parent
US=1000000
VIDEO={'.mp4','.webm','.mov','.mkv'}
AUDIO={'.mp3','.wav','.m4a','.aac','.flac','.ogg'}
def uid(): return str(uuid.uuid4()).upper()
def sortkey(p): return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)',p.name)]
def probe(p):
    cmd=['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]
    try: data=json.loads(subprocess.check_output(cmd,stderr=subprocess.STDOUT,timeout=35))
    except (FileNotFoundError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as e: raise RuntimeError(f'FFprobe no pudo analizar {p.name}: {e}')
    streams=data.get('streams',[])
    video=next((x for x in streams if x.get('codec_type')=='video'),None)
    dur=float(data.get('format',{}).get('duration') or (video or {}).get('duration') or 0)
    if dur<=0: raise ValueError('Duración inválida: '+str(p))
    return {'duration':round(dur*US),'width':int((video or {}).get('width',0)),'height':int((video or {}).get('height',0)), 'has_audio':any(x.get('codec_type')=='audio' for x in streams),'codec':(video or {}).get('codec_name','')}
def scan(folder,extensions): return sorted([p for p in pathlib.Path(folder).iterdir() if p.is_file() and p.suffix.lower() in extensions],key=sortkey)
def cloned(x):
    x=copy.deepcopy(x)
    x['id']=uid()
    if 'unique_id' in x: x['unique_id']=uuid.uuid4().hex
    return x

def parse_sticker_ids(value):
    if value is None: return []
    if isinstance(value,str):
        parts=re.split(r'[\s,;]+',value)
    else:
        try: parts=[str(x) for x in value]
        except TypeError: parts=[str(value)]
    ids=[p.strip() for p in parts if p and p.strip()]
    for sid in ids:
        if not sid.isdigit(): raise ValueError(f'ID de sticker inválido: {sid}')
    return ids

def sticker_settings(ids_value, interval_value=10.0, duration_value=3.0):
    ids=parse_sticker_ids(ids_value)
    if not ids: return ids,10.0,3.0
    try:
        interval=float(str(interval_value).replace(',','.'))
        duration=float(str(duration_value).replace(',','.'))
    except (TypeError,ValueError):
        raise ValueError('El intervalo y la duración de los stickers deben ser números.')
    if not math.isfinite(interval) or interval<=0:
        raise ValueError('El intervalo de stickers debe ser mayor que cero.')
    if not math.isfinite(duration) or duration<=0:
        raise ValueError('La duración de los stickers debe ser mayor que cero.')
    if duration>interval+1e-9:
        raise ValueError('La duración de los stickers no puede superar el intervalo.')
    return ids,interval,duration

def generate(vdir,adir,outdir,name='Generado_CapCut',strict=True,progress=None,trim_start=0.0,generic_video=None,generic_audio=None,generic_end_audio=None,generic_end_video=None,selected_videos=None,selected_audios=None,videos_per_chapter=4,sticker_ids=None,sticker_interval=10.0,sticker_duration=3.0):
    if type(videos_per_chapter) is not int or videos_per_chapter < 1: raise ValueError('Videos por capítulo debe ser un entero mayor que cero.')
    sticker_ids,sticker_interval,sticker_duration=sticker_settings(sticker_ids,sticker_interval,sticker_duration)
    def generic_block(video, audio, label):
        if any((video, audio)) and not all((video, audio)):
            raise ValueError(f'Selecciona un video y un audio para el {label}, o deja ambos vacíos.')
        if not video:
            return None
        vp, ap = pathlib.Path(video).resolve(), pathlib.Path(audio).resolve()
        if vp.suffix.lower() not in VIDEO or ap.suffix.lower() not in AUDIO:
            raise ValueError(f'Formato de video o audio no admitido en el {label}.')
        return (vp, probe(vp), ap, probe(ap))
    generic = {}
    block = generic_block(generic_video, generic_audio, 'bloque tras el capítulo 7')
    if block:
        generic['after_28'] = block
    block = generic_block(generic_end_video, generic_end_audio, 'bloque final')
    if block:
        generic['end'] = block
    generic = generic or None
    report_progress=progress or (lambda done,total,msg:None)
    def selected(paths, folder, extensions):
        if paths is None: return scan(folder,extensions)
        result=sorted([pathlib.Path(p).resolve() for p in paths],key=sortkey)
        if any(not p.is_file() or p.suffix.lower() not in extensions for p in result):
            raise ValueError('La selección contiene archivos inexistentes o de formato no admitido.')
        return result
    videos=selected(selected_videos,vdir,VIDEO); audios=selected(selected_audios,adir,AUDIO)
    if strict and (len(videos)!=40*videos_per_chapter or len(audios)!=40): raise ValueError(f'Se esperan {40*videos_per_chapter} videos y 40 audios; encontrados {len(videos)} y {len(audios)}.')
    if not audios or len(videos)!=len(audios)*videos_per_chapter: raise ValueError(f'Se necesitan exactamente {videos_per_chapter} videos por cada audio.')
    template=json.loads((ROOT/'templates/draft_content.json').read_text(encoding='utf-8'))
    meta=json.loads((ROOT/'templates/draft_meta_info.json').read_text(encoding='utf-8'))
    vt=next(t for t in template['tracks'] if t['type']=='video'); at=next(t for t in template['tracks'] if t['type']=='audio')
    vs=vt['segments'][0]; aus=at['segments'][0]
    mats=template['materials']; video_tpl=mats['videos'][0]; audio_tpl=mats['audios'][0]
    sticker_track_tpl=next((t for t in template['tracks'] if t['type']=='sticker'),None)
    sticker_tpl=next((m for m in mats.get('stickers',[]) if isinstance(m,dict)),None)
    sticker_seg_tpl=sticker_track_tpl['segments'][0] if sticker_track_tpl and sticker_track_tpl.get('segments') else None
    if sticker_ids and not (sticker_track_tpl and sticker_tpl and sticker_seg_tpl):
        raise ValueError('La plantilla no contiene un sticker de referencia para clonar.')
    # Build each segment's auxiliary materials using its reference IDs, preserving the exact original types.
    original_by_id={m['id']:m for arr in mats.values() if isinstance(arr,list) for m in arr if isinstance(m,dict) and 'id' in m}
    auxkeys=['speeds','canvases','beats','audio_fades','sound_channel_mappings','vocal_separations','material_colors','material_animations','placeholders','placeholder_infos']
    for k in mats:
        if isinstance(mats[k],list): mats[k]=[]
    track_v=copy.deepcopy(vt);track_v['id']=uid();track_v['segments']=[]
    track_a=copy.deepcopy(at);track_a['id']=uid();track_a['segments']=[]
    track_v['name']='Videos';track_a['name']='Narracion';track_v['is_default_name']=False;track_a['is_default_name']=False
    template['tracks']=[track_v,track_a]
    meta['draft_materials']=[{'type':0,'value':[]}]
    now=int(datetime.datetime.now().timestamp());cursor=0;report=[]
    trim_us=round(trim_start*US);total=len(videos)+len(audios)+1;done=0;allmedia=[];allaudio=[]
    for p in videos:
        allmedia.append((p,probe(p)));done+=1;report_progress(done,total,f'Analizando {p.name}')
    for p in audios:
        allaudio.append((p,probe(p)));done+=1;report_progress(done,total,f'Analizando {p.name}')
    def insert_generic(position):
        nonlocal cursor
        silent_lead = 3 * US; silent_tail = 3 * US
        vp, vi, ap, ai = generic[position]
        duration = ai['duration'] + silent_lead + silent_tail; source = min(vi['duration'], duration); speed = source / duration
        for path, info, tpl, segment_tpl, collection, track, kind, volume in [
            (vp, vi, video_tpl, vs, 'videos', track_v, 'video', 0.0),
            (ap, ai, audio_tpl, aus, 'audios', track_a, 'music', 1.0)
        ]:
            material = cloned(tpl)
            material.update(path=path.as_posix(),name=path.name,material_name=path.name,duration=info['duration'],width=info['width'],height=info['height'],has_audio=info['has_audio'],local_material_id=uid())
            mats[collection].append(material)
            segment = cloned(segment_tpl); rate = speed if kind == 'video' else 1.0
            segment.update(material_id=material['id'],source_timerange={'start':0,'duration':source if kind == 'video' else ai['duration']},target_timerange={'start':cursor + (0 if kind == 'video' else silent_lead),'duration':duration if kind == 'video' else ai['duration']},speed=rate,volume=volume)
            segment['extra_material_refs']=copy_aux(segment_tpl,mats,original_by_id,rate)
            track['segments'].append(segment)
            meta['draft_materials'][0]['value'].append(meta_entry(path,info,material['local_material_id'],now,kind))
        report.append({'type':'generic','position':position,'silent_lead_us':silent_lead,'silent_tail_us':silent_tail,'audio_start_us':cursor+silent_lead,'audio_duration_us':ai['duration'],'audio':ap.name,'video':vp.name,'start_us':cursor,'duration_us':duration,'speed':speed,'source_start_us':0,'source_us':source,'codec':vi['codec']})
        cursor += duration
    for i,(ap,ai) in enumerate(allaudio):
        ad=ai['duration'];start=cursor
        am=cloned(audio_tpl);am.update(path=ap.as_posix(),name=ap.name,duration=ad,local_material_id=uid())
        mats['audios'].append(am)
        seg=cloned(aus);seg['material_id']=am['id'];seg['source_timerange']={'start':0,'duration':ad};seg['target_timerange']={'start':start,'duration':ad};seg['speed']=1.0;seg['volume']=1.0
        seg['extra_material_refs']=copy_aux(aus,mats,original_by_id)
        track_a['segments'].append(seg)
        meta['draft_materials'][0]['value'].append(meta_entry(ap,ai,am['local_material_id'],now,'music'))
        for j in range(videos_per_chapter):
            vp,vi=allmedia[i*videos_per_chapter+j]
            left=ad*j//videos_per_chapter;right=ad*(j+1)//videos_per_chapter;allocated=right-left
            # Exact speed ratio; full source when slowing down, source trimmed when longer.
            # trim: se descarta siempre el arranque del clip (pausa inicial). Si aún sobra, se conserva el final.
            if allocated<=0: raise ValueError('La narración es demasiado corta para el número de videos.')
            usable=vi['duration']-trim_us
            if usable<=0: raise ValueError(f'{vp.name} dura menos que el recorte del inicio.')
            source=min(usable,allocated)
            src_start=vi['duration']-source
            speed=source/allocated
            vm=cloned(video_tpl);vm.update(path=vp.as_posix(),material_name=vp.name,duration=vi['duration'],width=vi['width'],height=vi['height'],has_audio=vi['has_audio'],local_material_id=uid())
            mats['videos'].append(vm)
            s=cloned(vs);s['material_id']=vm['id'];s['source_timerange']={'start':src_start,'duration':source};s['target_timerange']={'start':start+left,'duration':allocated};s['speed']=speed;s['volume']=0.0
            s['extra_material_refs']=copy_aux(vs,mats,original_by_id,speed)
            track_v['segments'].append(s)
            meta['draft_materials'][0]['value'].append(meta_entry(vp,vi,vm['local_material_id'],now,'video'))
            report.append({'audio':ap.name,'video':vp.name,'start_us':start+left,'duration_us':allocated,'speed':speed,'source_start_us':src_start,'source_us':source,'codec':vi['codec']})
        cursor+=ad
        if generic and 'after_28' in generic and i+1 == 7 and i+1 < len(allaudio): insert_generic('after_28')
    if generic and 'end' in generic: insert_generic('end')
    if sticker_ids and cursor>0:
        track_s=copy.deepcopy(sticker_track_tpl);track_s['id']=uid();track_s['segments']=[];track_s['name']='Stickers';track_s['is_default_name']=False
        step=max(1,int(round(sticker_interval*US)));dur=max(1,int(round(sticker_duration*US)))
        start=0;index=0
        while start<cursor:
            seg_dur=min(dur,cursor-start);sid=sticker_ids[index%len(sticker_ids)]
            material=cloned(sticker_tpl)
            material.update(resource_id=sid,sticker_id=sid,name=f'Sticker {sid}',path='',icon_url='',preview_cover_url='',category_id='',category_name='',request_id='')
            if 'third_resource_id' in material: material['third_resource_id']=sid
            mats.setdefault('stickers',[]).append(material)
            segment=cloned(sticker_seg_tpl)
            segment.update(material_id=material['id'],source_timerange=None,target_timerange={'start':start,'duration':seg_dur},extra_material_refs=[])
            track_s['segments'].append(segment)
            report.append({'type':'sticker','resource_id':sid,'start_us':start,'duration_us':seg_dur})
            index+=1;start+=step
        template['tracks']=[track_v,track_s,track_a]
    template['id']=uid();template['name']=name;template['duration']=cursor
    template['group_container']=None if template.get('group_container') is None else template['group_container']
    template['relationships']=[]
    template['keyframes']={};template['keyframe_graph_list']=[]
    meta['draft_id']=uid();meta['draft_name']=name;meta['tm_duration']=cursor
    meta['tm_draft_create']=now;meta['tm_draft_modified']=now
    report_progress(total-1,total,'Escribiendo archivos del proyecto')
    dest=pathlib.Path(outdir)/name
    if dest.exists(): raise FileExistsError(f'Ya existe {dest}; elige otro nombre para no sobrescribir.')
    dest.mkdir(parents=True)
    meta['draft_fold_path']=dest.as_posix();meta['draft_root_path']=dest.parent.as_posix()
    (dest/'draft_content.json').write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'draft_meta_info.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'timeline_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    report_progress(total,total,'Completado')
    return dest,len(track_v['segments']),len(track_a['segments']),cursor

def copy_aux(seg,mats,by_id,speed=None):
    refs=[]
    for oldid in seg.get('extra_material_refs',[]):
        old=by_id.get(oldid)
        if not old: continue
        # Find the matching material collection in the original template by its type, not guessed order.
        kind=old.get('type','')
        destkey={'speed':'speeds','canvas_color':'canvases','canvas':'canvases','beats':'beats','audio_fade':'audio_fades','sound_channel_mapping':'sound_channel_mappings','vocal_separation':'vocal_separations','material_color':'material_colors','material_animation':'material_animations','placeholder_info':'placeholder_infos','placeholder':'placeholders'}.get(kind)
        if not destkey:
            # Some CapCut materials use a different type string; match based on source index.
            destkey=SOURCE_KIND.get(oldid)
        if not destkey: continue
        new=cloned(old)
        if destkey=='speeds' and speed is not None: new['speed']=speed;new['mode']=0;new['curve_speed']=None
        mats[destkey].append(new);refs.append(new['id'])
    return refs
SOURCE_KIND={}
def meta_entry(path,info,id_,now,kind):
    return {'ai_group_type':'','create_time':now,'duration':info['duration'],'enter_from':0,'extra_info':path.name,'file_Path':path.as_posix(),'height':info['height'],'id':id_,'import_time':now,'import_time_ms':now*1000000,'item_source':1,'material_color_tag':'','md5':'','metetype':kind,'roughcut_time_range':{'duration':info['duration'],'start':0},'sub_time_range':{'duration':-1,'start':-1},'type':0,'width':info['width']}

def init_kind():
    data=json.loads((ROOT/'templates/draft_content.json').read_text(encoding='utf-8'))
    for k,v in data['materials'].items():
        if isinstance(v,list):
            for x in v:
                if isinstance(x,dict) and 'id' in x: SOURCE_KIND[x['id']]=k

