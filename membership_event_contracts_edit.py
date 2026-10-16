from pathlib import Path
p=Path('events/api_views.py');s=p.read_text(encoding='utf-8')
s=s.replace('''        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )''','''        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only organization accounts can create events."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )''',1)
s=s.replace('''        except Organization.DoesNotExist:
            return Response(
                {
                    "detail": "Organization profile not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )''','''        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only ORGANIZATION users can view event registrations."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )''',1)
for oldmsg,newmsg in [
("Only ORGANIZATION users can update registration status.","Only ORGANIZATION users can update registration status."),
("Only ORGANIZATION users can mark event attendance.","Only ORGANIZATION users can mark event attendance."),
]:
 old='''        except Organization.DoesNotExist:
            return Response(
                {
                    "detail": "Organization profile not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )'''
 new=f'''        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {{"detail": "{newmsg}"}},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {{"detail": "Organization profile not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )'''
 s=s.replace(old,new,1)
s=s.replace('''        organization = get_request_organization(
            request, OrganizationCapability.MANAGE_EVENTS,
        )

        event = get_object_or_404(''','''        try:
            organization = get_request_organization(
                request, OrganizationCapability.MANAGE_EVENTS,
            )
        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only organization accounts can upload event media."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            organization = None

        event = get_object_or_404(''',1)
s=s.replace('''        except Organization.DoesNotExist:
            return Response([])
        events = Event.objects.filter(''','''        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only organizations can view managed events."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response([])
        events = Event.objects.filter(''',1)
p.write_text(s,encoding='utf-8')
