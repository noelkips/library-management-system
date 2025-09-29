from django.shortcuts import render, redirect, get_object_or_404


def home(request):
    """Render the home page."""
    return render(request, 'home.html')



