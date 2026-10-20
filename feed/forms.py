from django import forms

from .models import Post, Comment



class PostForm(forms.ModelForm):

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("caption", "").strip() or cleaned.get("image") or cleaned.get("video")):
            raise forms.ValidationError("Add some text, a photo, or a video before posting.")
        return cleaned


    class Meta:

        model = Post


        fields = [

            "caption",

            "image",

            "video",

            "post_type",

            "visibility",

            "location",

        ]


        widgets = {


            "caption": forms.Textarea(

                attrs={

                    "class": "form-control",

                    "rows": 4,

                    "placeholder":
                    "Share something about your talent..."

                }

            ),



            "image": forms.ClearableFileInput(

                attrs={

                    "class": "form-control"

                }

            ),



            "video": forms.ClearableFileInput(

                attrs={

                    "class": "form-control"

                }

            ),



            "post_type": forms.Select(

                attrs={

                    "class": "form-select"

                }

            ),



            "visibility": forms.Select(

                attrs={

                    "class": "form-select"

                }

            ),



            "location": forms.TextInput(

                attrs={

                    "class": "form-control",

                    "placeholder":
                    "Location"

                }

            ),

        }
        
        

class CommentForm(forms.ModelForm):


    class Meta:


        model = Comment


        fields = [

            "text"

        ]


        widgets = {


            "text": forms.TextInput(

                attrs={

                    "class":"form-control",

                    "placeholder":
                    "Write a comment..."

                }

            )

        }
