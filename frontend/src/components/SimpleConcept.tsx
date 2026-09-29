import {useState,useRef} from 'react';
import {Check, CircleHelp, Pencil, X, Save} from 'lucide-react';
import {api} from '../api/client';
import type {ReviewItem, ReviewTarget} from '../types';

const questions:Record<string,string> = {
  motivation:"Pourquoi c'est important ?",objects:'De quoi parle-t-on ?',actors:'Qui est concerné ?',
  actions:'Que fait-on ?',means:'Avec quels moyens ?',information:'Quelles informations sont utilisées ?',
  rules:'Quelles règles ou conditions ?',result:'Quel résultat est attendu ?'
};
const statuses={new:'Nouveau',known:'Déjà connu',review:'À vérifier',validated:'Validé',ignored:'Ignoré'};

function friendlyIssue(issue:string) {
  if(issue.includes('Champ non source')) return "ECUME a repéré une information, mais n'a pas retrouvé le passage exact qui la confirme. Le champ est resté vide.";
  if(issue.includes('Extrait justificatif absent')) return "ECUME n'a pas retrouvé de passage exact pour justifier ce concept. Vérifiez la source avant de le valider.";
  if(issue.includes('Regle incomplete')||issue.includes('regle non source')) return "ECUME a repéré une règle, mais n'a pas pu confirmer toutes ses valeurs, unités ou conditions.";
  if(issue.includes('retire ou modifie')) return "Le concept auquel cette mention était rattachée a changé. Choisissez une nouvelle cible.";
  return issue;
}

function issueGroups(issues:string[]) {
  const fieldCount=issues.filter(issue=>issue.includes('Champ non source')).length;
  const sourceCount=issues.filter(issue=>issue.includes('Extrait justificatif absent')).length;
  const ruleCount=issues.filter(issue=>issue.includes('Regle incomplete')||issue.includes('regle non source')).length;
  const covered=fieldCount+sourceCount+ruleCount;
  const summaries:string[]=[];
  if(fieldCount)summaries.push(`${fieldCount} champ${fieldCount>1?'s':''} non confirmé${fieldCount>1?'s':''}`);
  if(sourceCount)summaries.push(`${sourceCount} proposition${sourceCount>1?'s':''} sans extrait exact`);
  if(ruleCount)summaries.push(`${ruleCount} règle${ruleCount>1?'s':''} ou valeur${ruleCount>1?'s':''} de règle à vérifier`);
  if(issues.length>covered)summaries.push(`${issues.length-covered} autre${issues.length-covered>1?'s':''} point${issues.length-covered>1?'s':''} à vérifier`);
  const details=[...issues.reduce((grouped,issue)=>{
    const message=friendlyIssue(issue);grouped.set(message,(grouped.get(message)??0)+1);return grouped;
  },new Map<string,number>())];
  return {summaries,details};
}

function decisionText(item:ReviewItem, needsIdentityChoice:boolean) {
  if(item.status==='new') return "ECUME n'a pas trouvé de concept identique dans la connaissance existante. Validez si cette notion mérite d'être conservée.";
  if(item.status==='known') return "ECUME a reconnu cette mention et l'a rattachée à un concept existant. Aucun doublon ne sera créé.";
  if(item.status==='review'&&needsIdentityChoice) return "ECUME hésite entre cette mention et un concept proche. Choisissez le bon rattachement avant de poursuivre.";
  if(item.status==='review') return "ECUME n'a pas pu confirmer une partie de cette proposition. Consultez la source, puis validez ou corrigez avec votre expertise.";
  if(item.status==='validated') return "Ce concept a été ajouté à la connaissance validée. Il reste modifiable si vous constatez une incohérence.";
  return "Cette proposition a été ignorée et n'alimente pas la connaissance validée.";
}

export default function SimpleConcept({item,onChanged}:{item:ReviewItem;onChanged:()=>void}) {
  const [editing,setEditing]=useState(false),[repair,setRepair]=useState(false);
  const [editingField,setEditingField]=useState<string|null>(null);
  const [extraField,setExtraField]=useState<string>("");
  const [fieldRepair,setFieldRepair]=useState<{key:string;index:number}|null>(null);
  const [showQualification,setShowQualification]=useState(false);
  const [label,setLabel]=useState(item.label),[description,setDescription]=useState(item.description);
  const [fields,setFields]=useState<Record<string,string>>({});
  const [query,setQuery]=useState(''),[targets,setTargets]=useState<ReviewTarget[]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const searchVersion=useRef(0);
  async function act(payload:Record<string,unknown>){
    setBusy(true);setError('');
    try{await api.decideMention(item.id,payload);setEditing(false);setRepair(false);onChanged();}
    catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  function repairAction(payload:Record<string,unknown>){return act({...payload,...(fieldRepair?{field_key:fieldRepair.key,field_index:fieldRepair.index}:{})});}
  const repairValue=fieldRepair?item.fields[fieldRepair.key][fieldRepair.index]:null;
  const repairTarget=repairValue?.target??(!fieldRepair?item.target:null);
  const candidates=repairValue?.candidates??(!fieldRepair?item.candidates:[]);
  const filled=Object.keys(questions).filter(key=>item.fields[key]?.length);
  const missing=Object.entries(questions).filter(([key])=>!item.fields[key]?.length).map(([,title])=>title);
  const needsIdentityChoice=!item.card_id&&!item.target&&Boolean(item.candidates[0]?.score!==undefined&&item.candidates[0].score>=.7);
  const mappingUnknown=!item.archimate_mapping||item.archimate_mapping.candidate_element==='Unknown';
  const groupedIssues=issueGroups(item.issues);
  function edit(field:string|null=null){setLabel(item.label);setDescription(item.description);setFields(Object.fromEntries(Object.keys(questions).map(k=>[k,(item.fields[k]??[]).map(v=>v.text).join('\n')])));setEditingField(field);setExtraField("");setEditing(true);}
  const qualificationOptions=<div className="qualification-choices" role="group" aria-label="Signification métier du concept">
    {(item.qualification_choices??[]).map(choice=><button className="qualification-choice" key={choice.category} disabled={busy} onClick={()=>void act({action:'qualify',business_category:choice.category})}>
      <span><strong>{choice.label}</strong>{choice.recommended&&<small>Choix suggéré</small>}</span>
      <span>{choice.explanation}</span>
    </button>)}
  </div>;

  return <article className="simple-concept">
    <div className="section-title"><h3>{item.label}</h3><span className={`simple-state state-${item.status}`}>{statuses[item.status]}</span></div>

    <section className="concept-reading">
      <h4>ECUME a compris</h4>
      <p className="concept-summary">{item.description||('Le document mentionne « '+item.label+' », sans fournir de résumé suffisamment fiable.')}</p>
    </section>

    {item.status==='known'&&item.target&&<p className="canonical-match">
      <span>Mention du document : <strong>{item.label}</strong></span>
      <span>Concept retenu : <strong>{item.target.label}</strong></span>
      <span className="simple-state">{item.target.kind==='echo'?'Déjà présent dans Echo':'Déjà connu dans ECUME'}</span>
      <button className="ghost-button icon-button" title="Corriger le rattachement" aria-label={'Corriger le rattachement de '+item.label} onClick={()=>{setFieldRepair(null);setRepair(!repair);}}><Pencil size={16}/></button>
    </p>}

    {!item.target&&item.candidates.length>0&&<section className="close-concepts">
      <div className="section-title"><h4>Concepts proches trouvés</h4><span>{item.candidates.length}</span></div>
      <p className="quiet-note">ECUME propose des rapprochements, mais vous gardez la décision.</p>
      <ul>{item.candidates.slice(0,3).map(candidate=><li key={candidate.id}>
        <div><strong>{candidate.label}</strong>{candidate.score!==undefined&&<span className="match-score">{Math.round(candidate.score*100)} %</span>}
          <small>{candidate.reason||"Libellé ou définition proche."}</small><small>Source : {candidate.source||candidate.repository_name||(candidate.kind==='echo'?"référentiel Echo":"graphe ECUME")}</small></div>
        <div className="button-row"><button disabled={busy} onClick={()=>void act({action:'attach',target_id:candidate.id})}>Rattacher</button>
          <button className="ghost-button" disabled={busy} onClick={()=>void act({action:'alias',target_id:candidate.id})}>{candidate.kind==='echo'?'Proposer comme synonyme':'Conserver comme synonyme'}</button></div>
      </li>)}</ul>
      <div className="button-row"><button className="ghost-button" disabled={busy} onClick={()=>void act({action:'new'})}>Créer un nouveau concept</button>
        <button className="ghost-button" disabled={busy} onClick={()=>void act({action:'dismiss'})}>Ignorer ces rapprochements</button>
        {item.candidates.length>3&&<button className="ghost-button" onClick={()=>{setFieldRepair(null);setRepair(true);}}>Voir les autres</button>}</div>
    </section>}

    {!editing&&filled.length>0&&<dl className="business-fields">{Object.entries(questions).filter(([key])=>item.fields[key]?.length).map(([key,title])=><div className="business-field" key={key}><dt>{title}</dt><dd>{item.fields[key].map((v,index)=><div className="business-value" key={index}>{v.text}{v.target&&<small className="field-target">Rattaché à : {v.target.label} · {v.target.kind==='echo'?'déjà connu dans Echo':'déjà connu dans ECUME'}</small>}{v.status==='review'&&<small className="field-target">Rattachement à vérifier</small>}</div>)}{!item.id.startsWith('legacy:')&&<button className="field-edit-button" onClick={()=>edit(key)}><Pencil size={14}/>Modifier cette liste</button>}</dd></div>)}</dl>}

    <section className="decision-guide">
      <h4>{['validated','ignored'].includes(item.status)?"Ce qu'il s'est passé":'Ce que vous devez décider'}</h4>
      <p>{decisionText(item,needsIdentityChoice)}</p>
    </section>

    {item.issues.length>0&&<section className="ecume-limit" role="note">
      <h4>Ce qu'ECUME n'a pas pu confirmer</h4>
      <p>ECUME a laissé certains champs vides car aucun extrait fiable ne les confirme.</p>
      <ul className="issue-summary">{groupedIssues.summaries.map(summary=><li key={summary}>{summary}</li>)}</ul>
      <details><summary>Voir le détail</summary><ul>{groupedIssues.details.map(([message,count])=><li key={message}>{count>1&&<strong>{count} × </strong>}{message}</li>)}</ul></details>
    </section>}

    <details className="result-explanation">
      <summary><CircleHelp size={15}/>Comprendre ce résultat</summary>
      <p>ECUME a renseigné {filled.length} rubrique{filled.length>1?'s':''} sur {Object.keys(questions).length} à partir du document.</p>
      {missing.length>0&&<p><strong>Non trouvé dans le texte :</strong> {missing.join(' · ')}. Ces rubriques restent vides pour éviter d'inventer.</p>}
      {!item.source_excerpt&&<p>Aucun extrait exact n'a pu être conservé pour cette proposition.</p>}
      {item.status==='known'&&<p>« Déjà connu » signifie que le document apporte une nouvelle occurrence ou une nouvelle source, mais pas un nouveau concept.</p>}
    </details>

    {item.status!=='known'&&mappingUnknown&&!!item.qualification_choices?.length&&<section className="qualification-prompt">
      <h4>ECUME hésite sur la nature de ce concept</h4>
      <p>Choisissez son sens métier. ECUME préparera ensuite automatiquement sa traduction vers les modèles techniques.</p>
      {showQualification?qualificationOptions:<button className="ghost-button" onClick={()=>setShowQualification(true)}>Voir les {item.qualification_choices.length} propositions</button>}
    </section>}

    {item.source_excerpt&&<details className="simple-source"><summary>Voir le passage source{item.document_title?' : '+item.document_title:''}</summary><blockquote>{item.source_excerpt}</blockquote></details>}
    {!!item.business_rules?.length&&<details><summary>Règles détectées ({item.business_rules.length})</summary>{item.business_rules.map((rule,i)=><p key={i}>{rule.label} {rule.value} {rule.unit}{rule.condition&&' · '+rule.condition}{rule.exception&&' · Exception : '+rule.exception}</p>)}</details>}

    {editing ? <form className="concept-editor" onSubmit={e=>{e.preventDefault();void act({action:'update',label,description,preserve_identity:!!editingField,fields:Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.split('\n').filter(Boolean)]))});}}>
      <p className="compact-editor-note">Vous n’êtes pas obligé de tout remplir. Corrigez seulement ce qui est utile.</p>
      {!editingField&&<><label>Concept métier<input required maxLength={240} value={label} onChange={e=>setLabel(e.target.value)}/></label>
      <label>ECUME a compris<textarea value={description} onChange={e=>setDescription(e.target.value)}/></label></>}
      <div className="business-fields">{Object.entries(questions).filter(([key])=>(editingField?key===editingField:Boolean(fields[key]?.trim())||key===extraField)&&(!item.id.startsWith('legacy:')||['objects','actions','rules'].includes(key))).map(([key,title])=><label key={key}>{title}<textarea value={fields[key]??''} placeholder="Non renseigné" onChange={e=>setFields({...fields,[key]:e.target.value})}/></label>)}</div>
      {!editingField&&<label className="add-field">Ajouter une information facultative<select value={extraField} onChange={e=>setExtraField(e.target.value)}><option value="">Choisir une question</option>{Object.entries(questions).filter(([key])=>!fields[key]?.trim()).map(([key,title])=><option key={key} value={key}>{title}</option>)}</select></label>}
      {editingField&&item.fields[editingField]?.some(value=>value.target||value.status==='review')&&<details className="mapping-editor"><summary>Modifier un rattachement existant</summary>{item.fields[editingField].map((value,index)=><div key={index}><span>{value.text}{value.target&&` → ${value.target.label}`}</span><button type="button" className="ghost-button" onClick={()=>{setEditing(false);setFieldRepair({key:editingField,index});setQuery('');setTargets([]);setRepair(true);}}>Changer le rattachement</button></div>)}</details>}
      <div className="button-row"><button disabled={busy}><Save size={16}/>Enregistrer</button><button type="button" className="ghost-button" onClick={()=>setEditing(false)}>Annuler</button></div>
    </form> : item.status!=='known'&&<div className="button-row card-actions">
      {item.status!=='validated'&&!needsIdentityChoice&&<button disabled={busy} onClick={()=>void act({action:'accept'})}><Check size={16}/>Valider</button>}
      <button className="ghost-button" disabled={busy} onClick={()=>edit()}><Pencil size={16}/>Corriger la carte</button>
      {item.status!=='ignored'&&<button className="ghost-button" disabled={busy} onClick={()=>void act({action:'ignore'})}><X size={16}/>Ignorer</button>}
      {needsIdentityChoice&&<button disabled={busy} onClick={()=>{setFieldRepair(null);setRepair(true);}}>Choisir le rattachement</button>}
    </div>}

    {repair&&<section className="mention-repair"><h4>À quel concept faut-il rattacher cette mention ?</h4>
      {repairTarget&&<button className="ghost-button" onClick={()=>setRepair(false)}>Garder le rattachement actuel</button>}
      <label>Rechercher un autre concept<input value={query} placeholder="Saisir au moins 2 caractères" onChange={async e=>{const q=e.target.value;const version=++searchVersion.current;setQuery(q);try{const next=await api.reviewTargets(q);if(version===searchVersion.current)setTargets(next);}catch(err){setError(String(err));}}}/></label>
      <ul className="target-results">{(query.length>=2?targets:candidates).slice(0,8).map(t=><li key={t.id}><button className="ghost-button" disabled={busy} onClick={()=>void repairAction({action:'attach',target_id:t.id})}><strong>{t.label}</strong><span>{t.kind==='echo'?'Echo':'ECUME'}</span><small>{t.description?.slice(0,160)}</small></button></li>)}</ul>
      <button className="ghost-button" disabled={busy} onClick={()=>void repairAction({action:'new'})}>Créer un nouveau concept</button>
      <button className="ghost-button" onClick={()=>setRepair(false)}>Fermer</button>
    </section>}

    {error&&<p className="error" role="alert">{error}</p>}

    {item.archimate_mapping&&<details className="advanced-details">
      <summary>Détails avancés</summary>
      {mappingUnknown?<p>Aucune traduction technique fiable n'est encore proposée pour ce concept.</p>:<>
        <p><strong>Interprétation actuelle :</strong> {item.archimate_mapping.candidate_layer} / {item.archimate_mapping.candidate_element} (candidat)</p>
        <p>{item.archimate_mapping.reason}</p>
      </>}
      {item.status!=='known'&&!mappingUnknown&&showQualification&&qualificationOptions}
      {item.status!=='known'&&!mappingUnknown&&!showQualification&&<button className="ghost-button" onClick={()=>setShowQualification(true)}>Revoir cette interprétation</button>}
      {item.target?.kind==='echo'&&<p>Correspondance Echo : {item.target.label}</p>}
    </details>}
  </article>;
}
