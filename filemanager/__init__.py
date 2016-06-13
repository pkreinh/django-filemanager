# coding:utf-8
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _
from django.http import HttpResponseRedirect, HttpResponse
from django.template import RequestContext
#from django.core.servers.basehttp import FileWrapper
from wsgiref.util import FileWrapper
from django import forms
from PIL import Image
import settings
import mimetypes
import os
import shutil
import re
import tarfile

path_end = r'(?P<path>[\w\d_ -/.]*)$'

ActionChoices = (
    ('upload',_(u'hochladen')),
    ('rename',_(u'umbenennen')),
    ('delete',_(u'löschen')),
    ('add',_(u'hinzufügen')),
    ('move',_(u'verschieben')),
    ('copy',_(u'kopieren')),
  )

class FileManagerForm(forms.Form):
  ufile = forms.FileField(required=False)
  action = forms.ChoiceField(choices=ActionChoices)
  path = forms.CharField(max_length=200,required=False)
  name = forms.CharField(max_length=32,required=False)
  current_path = forms.CharField(max_length=200,required=False)
  file_or_dir = forms.CharField(max_length=4)

class FileManager(object):
  """
  maxspace,maxfilesize in KB
  """
  idee = 0
  def __init__(self,basepath,ckeditor_baseurl='',maxfolders=50,maxspace=5*1024,maxfilesize=1*1024,public_url_base=None,extensions=None,template='filemanager/index.html'):
    if basepath[-1] == '/':
      basepath = basepath[:-1]
    if ckeditor_baseurl and ckeditor_baseurl[-1] == '/':
      ckeditor_baseurl = ckeditor_baseurl[:-1]
    self.basepath = basepath
    self.ckeditor_baseurl = ckeditor_baseurl
    self.maxfolders = maxfolders
    self.maxspace = maxspace
    self.maxfilesize = maxfilesize
    self.extensions = extensions;
    self.public_url_base = public_url_base
    self.template = template

  def rename_if_exists(self,folder,file):
    if folder[-1] != os.sep:
      folder = folder + os.sep
    if os.path.exists(folder+file):
      if file.find('.') == -1:
        # no extension
        for i in range(1000):
          if not os.path.exists(folder+file+'.'+str(i)):
            break
        return file+'.'+str(i)
      else:
        extension = file[file.rfind('.'):]
        name = file[:file.rfind('.')]
        for i in range(1000):
          if not os.path.exists(folder+name+'.'+str(i)+extension):
            break
        return name + '.' + str(i) + extension
    else:
      return file

  def get_size(self,start_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
      for f in filenames:
        fp = os.path.join(dirpath, f)
        total_size += os.path.getsize(fp)
    return total_size

  def next_id(self):
    self.idee = self.idee+1
    return self.idee

  def handle_form(self,form,files):
    action = form.cleaned_data['action']
    path   = form.cleaned_data['path']
    name   = form.cleaned_data['name']
    ufile = form.cleaned_data['ufile']
    file_or_dir = form.cleaned_data['file_or_dir']
    self.current_path = form.cleaned_data['current_path']
    messages = []
    if name and file_or_dir == 'dir' and not re.match(r'[\w\d_ -]+',name).group(0) == name:
      messages.append(_(u'Ungültiger Ordnername : %(name)s') % {'name': name})
      return messages
    if name and file_or_dir == 'file' and (re.search('\.\.',name) or not re.match(r'[\w\d_ -.]+',name).group(0) == name):
      messages.append(_(u'Ungültiger Dateiname : %(name)s') % {'name': name})
      return messages
    if not re.match(r'[\w\d_ -/]+',path).group(0) == path:
      messages.append(_(u'Ungültige Pfadangabe : %(path)s') % {'path': name})
      return messages
    if action == 'upload':
      for f in files.getlist('ufile'):
        if re.search('\.\.',f.name) or not re.match('[\w\d_ -/.]+',f.name).group(0) == f.name:
          messages.append(_(u'Ungültiger Dateiname : %(name)s') % {'name': f.name})
        elif f.size > self.maxfilesize*1024:
          messages.append(_(u'Dateigröße überschritten %(max) KB : %(name)s') % {'max': self.maxfilesize, 'name': f.name})
        elif (settings.FILEMANAGER_CHECK_SPACE and
             ((self.get_size(self.basepath)+f.size) > self.maxspace*1024)):
          messages.append(_(u'Zulässige Speicherplatzgröße überschritten %(max) KB : %(name)s') % {'max': self.maxspace, 'name': f.name})
        elif self.extensions and len(f.name.split('.'))>1 and f.name.split('.')[-1] not in self.extensions:
            messages.append(_(u'Dateinamenerweiterung (Suffix) nicht erlaubt (%(suffix)) : %(name)') % {'suffix': f.name.split('.')[-1], 'name': f.name})
        elif self.extensions and len(f.name.split('.'))==1 and f.name.split('.')[-1] not in self.extensions:
            messages.append(_(u'Keine Dateinamenerweiterung (Suffix) in der hochgeladenen Datei : %(name)') % {'name': f.name})
        else:
          filepath = self.basepath+path+self.rename_if_exists(self.basepath+path,f.name)
          with open(filepath,'w') as dest:
            for chunk in f.chunks():
              dest.write(chunk)
          f.close()
      if len(messages) == 0:
        messages.append(_(u'Alle Dateien erfolgreich hoch geladen'))
    elif action == 'add':
      os.chdir(self.basepath)
      no_of_folders = len(list(os.walk('.')))
      if (no_of_folders + 1) <= self.maxfolders:
        try:
          os.chdir(self.basepath+path)
          os.mkdir(name)
          messages.append(_(u'Ordner erfolgreich angelegt: %(name)s') % {'name': name})
        except:
          messages.append(_(u'Ordner konnte nicht angelegt werden: %(name)s') % {'name': name})
      else:
        messages.append(_(u'Ordner konnte nicht angelegt werden da maximal Anzahl erreicht: %(max)s') % {'max': self.maxfolders})
    elif action == 'rename' and file_or_dir == 'dir':
      oldname = path.split('/')[-2]
      path = '/'.join(path.split('/')[:-2])
      try:
        os.chdir(self.basepath+path)
        os.rename(oldname,name)
        messages.append(_(u'Ordner erfolgreich umbenannt von %(alt)s nach %(neu)s') % {'alt': oldname, 'neu' :name})
      except:
        messages.append(_(u'Ordner konnte nicht auf %(name)s umbenannt werden') % {'name': name})
    elif action == 'delete' and file_or_dir == 'dir':
      if path =='/':
        messages.append(_(u'root Ordner kann nicht gelöscht werden'))
      else:
        name = path.split('/')[-2]
        path = '/'.join(path.split('/')[:-2])
        try:
          os.chdir(self.basepath+path)
          shutil.rmtree(name)
          messages.append(_(u'Ordner erfolgreich gelöscht : %(name)s') % {'name': name})
        except:
          messages.append(_(u'Ordner konnte nich gelöscht werden : %(name)s') % {'name': name})
    elif action == 'rename' and file_or_dir == 'file':
      oldname = path.split('/')[-1]
      old_ext = oldname.split('.')[1] if len(oldname.split('.'))>1 else None
      new_ext = name.split('.')[1] if len(name.split('.'))>1 else None
      if old_ext == new_ext:
        path = '/'.join(path.split('/')[:-1])
        try:
          os.chdir(self.basepath+path)
          os.rename(oldname,name)
          messages.append(_(u'Datei erfolgreich umbenannt von %(alt)s nach %(neu)s') % {'alt': oldname, 'neu' :name})
        except:
          messages.append(_(u'Datei konnte nicht auf %(name)s umbenannt werden') % {'name': name})
      else:
        if old_ext:
          messages.append(_(u'Die Dateierweiterung (Suffix) sollte gleich sein : %(suffix)s ') % {'suffix': old_ext})
        else:
          messages.append(_(u'Die neue Datie hat nicht die selbe Dateierweiterung (Suffix)'))
    elif action == 'delete' and file_or_dir == 'file':
      if path =='/':
        messages.append(_(u'root Ordner kann nicht gelöscht werden'))
      else:
        name = path.split('/')[-1]
        path = '/'.join(path.split('/')[:-1])
        try:
          os.chdir(self.basepath+path)
          os.remove(name)
          messages.append(_(u'Datei erfolgreich gelöscht : %(name)s') % {'name': name})
        except:
          messages.append(_(u'Datei konnte nich gelöscht werden : %(name)s') % {'name': name})
    elif action == 'move' or action == 'copy':
      # from path to current_path
      if self.current_path.find(path) == 0:
        messages.append(_(u'Unterordner kann nicht verschoben/kopiert werden'))
      else :
        path = os.path.normpath(path) # strip trailing slash if any
        if os.path.exists(self.basepath+self.current_path+os.path.basename(path)):
          messages.append('Fehler: Eine Datei/Ordner mit diesem Namen existiert schon im Zielordner.')
        else:
          if action == 'move':
            method = shutil.move
          else:
            if file_or_dir == 'dir':
              method = shutil.copytree
            else:
              method = shutil.copy
          try:
            method(self.basepath+path, self.basepath+self.current_path+os.path.basename(path))
          except:
            messages.append('Datei/Ordner kann nicht verschoben/kopiert werden.')
    return messages

  def directory_structure(self):
    self.idee = 0
    dir_structure = {'':{'id':self.next_id(),'open':'yes','dirs':{},'files':[]}}
    os.chdir(self.basepath)
    for directory,directories,files in os.walk('.'):
      directory_list = directory[1:].split('/')
      current_dir = None
      nextdirs = dir_structure
      for d in directory_list:
        current_dir = nextdirs[d]
        nextdirs = current_dir['dirs']
      if directory[1:]+'/' == self.current_path:
        self.current_id = current_dir['id']
      current_dir['dirs'].update(dict(map(lambda d:(d,{'id':self.next_id(),'open':'no','dirs':{},'files':[]}),directories)))
      current_dir['files'] = files
    return dir_structure

  def media(self,path):
    ext = path.split('.')[-1]
    try:
      mimetypes.init()
      mimetype = mimetypes.guess_type(path)[0]
      img = Image.open(self.basepath+'/'+path)
      width,height = img.size
      mx = max([width,height])
      w,h = width,height
      if mx > 60:
        w = width*60/mx
        h = height*60/mx
      img = img.resize((w,h), Image.ANTIALIAS)
      response = HttpResponse(content_type = mimetype or "image/"+ext)
      response['Cache-Control'] = 'max-age=3600'
      img.save(response,mimetype.split('/')[1] if mimetype else ext.upper())
      return response
    except Exception as e:
      imagepath = settings.FILEMANAGER_STATIC_ROOT+'images/icons/'+ext+'.png'
      if not os.path.exists(imagepath):
        imagepath = settings.FILEMANAGER_STATIC_ROOT+'images/icons/default.png'
      img = Image.open(imagepath)
      width,height = img.size
      mx = max([width,height])
      w,h = width,height
      if mx > 60:
        w = width*60/mx
        h = height*60/mx
      img = img.resize((w,h), Image.ANTIALIAS)
      response = HttpResponse(content_type="image/png")
      response['Cache-Control'] = 'max-age:3600'
      img.save(response,'png')
      return response

  def download(self,path,file_or_dir):
    if not re.match(r'[\w\d_ -/]*',path).group(0) == path:
      return HttpResponse('Invalid path')
    if file_or_dir == 'file':
      filepath = self.basepath + '/' + path
      wrapper = FileWrapper(file(filepath))
      response = HttpResponse(wrapper, content_type=mimetypes.guess_type(filepath)[0])
      response['Content-Length'] = os.path.getsize(filepath)
      response['Content-Disposition'] = 'attachment; filename='+path.split('/')[-1]
      return response
    elif file_or_dir == 'dir':
      dirpath = self.basepath + '/' + path
      dirname = dirpath.split('/')[-2]
      response = HttpResponse(content_type='application/x-gzip')
      response['Content-Disposition'] = 'attachment; filename=%s.tar.gz' % dirname
      tarred = tarfile.open(fileobj=response, mode='w:gz')
      tarred.add(dirpath,arcname=dirname)
      tarred.close()
      return response

  def render(self,request,path):
    if request.GET.has_key('download'):
      return self.download(path,request.GET['download'])
    if path:
      return self.media(path)
    CKEditorFuncNum = request.GET.get('CKEditorFuncNum','')
    messages = []
    self.current_path = '/'
    self.current_id = 1
    if request.method == 'POST':
      form = FileManagerForm(request.POST,request.FILES)
      if form.is_valid():
        messages = self.handle_form(form,request.FILES)
    if settings.FILEMANAGER_CHECK_SPACE:
        space_consumed = self.get_size(self.basepath)
    else:
        space_consumed = 0
    return render(request, self.template, {
        'dir_structure': self.directory_structure(),
        'messages':map(str,[e.encode('ascii', 'xmlcharrefreplace') for e in messages]),
        'current_id':self.current_id,
        'CKEditorFuncNum':CKEditorFuncNum,
        'ckeditor_baseurl':self.ckeditor_baseurl,
        'public_url_base':self.public_url_base,
        'space_consumed':space_consumed,
        'max_space':self.maxspace,
        'show_space':settings.FILEMANAGER_SHOW_SPACE,
    })
