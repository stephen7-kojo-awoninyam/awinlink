from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import PortfolioItem
from .forms import PortfolioItemForm
from talents.models import TalentProfile
# Create your views here.




@login_required
def add_portfolio_item(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    if request.method == "POST":


        form = PortfolioItemForm(

            request.POST,

            request.FILES

        )


        if form.is_valid():


            item = form.save(

                commit=False

            )


            item.talent = talent


            item.save()


            return redirect(

                "talent_dashboard"

            )


    else:

        form = PortfolioItemForm()



    return render(

        request,

        "portfolio/add.html",

        {

            "form": form

        }

    )
    
    
    
@login_required
def portfolio_list(request):


    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    items = PortfolioItem.objects.filter(
        talent=talent
    ).order_by(
        "-created_at"
    )


    return render(

        request,

        "portfolio/list.html",

        {
            "items": items
        }

    )  
    
@login_required
def edit_portfolio_item(request, item_id):


    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    item = get_object_or_404(
        PortfolioItem,
        id=item_id,
        talent=talent
    )


    if request.method == "POST":


        form = PortfolioItemForm(

            request.POST,

            request.FILES,

            instance=item

        )


        if form.is_valid():

            form.save()

            return redirect(
                "portfolio_list"
            )


    else:


        form = PortfolioItemForm(
            instance=item
        )


    return render(

        request,

        "portfolio/edit.html",

        {
            "form": form
        }

    )
    
@login_required
def delete_portfolio_item(request, item_id):


    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    item = get_object_or_404(
        PortfolioItem,
        id=item_id,
        talent=talent
    )


    item.delete()


    return redirect(
        "portfolio_list"
    )          