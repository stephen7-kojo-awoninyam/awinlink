import ast
import textwrap
from pathlib import Path
p=Path('events/api_views.py')
source=p.read_text(encoding='utf-8')

def update_method(class_name, method_name, callback):
    global source
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method_name)
    lines=source.splitlines(keepends=True)
    begin=sum(len(x) for x in lines[:node.lineno-1])
    end=sum(len(x) for x in lines[:node.end_lineno])
    chunk=source[begin:end]
    chunk=callback(chunk)
    source=source[:begin]+chunk+source[end:]

def drop_global_role_guard(chunk):
    tree=ast.parse(textwrap.dedent(chunk))
    lines=chunk.splitlines(keepends=True)
    spans=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.If) and ast.unparse(n.test)=='request.user.role != "ORGANIZATION"':
            spans.append((n.lineno,n.end_lineno))
    for start,end in reversed(spans):
        del lines[start-1:end]
    return ''.join(lines)

def replace_active_org(chunk, capability, object_expr=None):
    import re
    expr=(
        f'get_request_organization(request, OrganizationCapability.{capability}, organization={object_expr})'
        if object_expr else
        f'get_request_organization(request, OrganizationCapability.{capability})'
    )
    return re.sub(
        r'require_active_organization\(getattr\(\s*request.user,\s*"organization_profile",\s*None\s*\)\)',
        expr,
        chunk,
        count=1,
    )

# Create keeps its existing 400 response when the account has no organization.
def create(chunk):
    chunk=drop_global_role_guard(chunk)
    old='''organization = require_active_organization(getattr(
            request.user,
            "organization_profile",
            None
        ))'''
    new='''try:
            organization = get_request_organization(
                request, OrganizationCapability.MANAGE_EVENTS,
            )
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )'''
    assert old in chunk
    return chunk.replace(old,new,1)
update_method('EventCreateAPIView','post',create)

for cls,method in [('EventUpdateAPIView','put'),('EventDeleteAPIView','delete')]:
    update_method(cls,method,lambda chunk: replace_active_org(
        drop_global_role_guard(chunk),'MANAGE_EVENTS','event.organizer'
    ))
for cls,method,cap in [
 ('EventRegistrationListAPIView','get','VIEW_EVENTS'),
 ('EventRegistrationStatusAPIView','patch','MANAGE_EVENTS'),
 ('EventAttendanceAPIView','post','MANAGE_EVENTS'),
 ('EventMediaCreateAPIView','post','MANAGE_EVENTS'),
]:
    def transform(chunk,cap=cap):
        chunk=drop_global_role_guard(chunk)
        chunk=chunk.replace(
            'require_active_organization(request.user.organization_profile)',
            f'get_request_organization(request, OrganizationCapability.{cap})',
        )
        return chunk
    update_method(cls,method,transform)

def my_events(chunk):
    chunk=drop_global_role_guard(chunk)
    old='''        require_user_organization_active(request.user)
        events = Event.objects.filter(
            organizer__user=request.user
        ).select_related("organizer", "category").order_by("-created_at")
        return Response(EventSerializer(events, many=True).data)'''
    new='''        try:
            organization = get_request_organization(
                request, OrganizationCapability.VIEW_EVENTS,
            )
        except Organization.DoesNotExist:
            return Response([])
        events = Event.objects.filter(
            organizer=organization
        ).select_related("organizer", "category").order_by("-created_at")
        return Response(EventSerializer(events, many=True).data)'''
    assert old in chunk
    return chunk.replace(old,new)
update_method('MyOrganizationEventsAPIView','get',my_events)
p.write_text(source,encoding='utf-8')
