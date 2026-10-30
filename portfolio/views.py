from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import PortfolioItem
from .forms import PortfolioItemForm
from .permissions import owned_portfolio_talent_for, owned_portfolio_item_for
from django.views.decorators.cache import never_cache
# Create your views here.




@login_required
@never_cache
def add_portfolio_item(request):


    talent = owned_portfolio_talent_for(request.user)


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
@never_cache
def portfolio_list(request):


    talent = owned_portfolio_talent_for(request.user)


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
@never_cache
def edit_portfolio_item(request, item_id):


    item = owned_portfolio_item_for(request.user, item_id)


    if request.method == "POST":


        form = PortfolioItemForm(

            request.POST,

            request.FILES,

            instance=item

        )


        if form.is_valid():
            from media_erasure.services import save_instance_with_media_retention
            save_instance_with_media_retention(item, form.save, requested_by_id=request.user.pk)

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
@require_POST
def delete_portfolio_item(request, item_id):


    item = owned_portfolio_item_for(request.user, item_id)
    from media_erasure.services import delete_instance_with_retention
    delete_instance_with_retention(item, requested_by_id=request.user.pk)


    return redirect(
        "portfolio_list"
    )
